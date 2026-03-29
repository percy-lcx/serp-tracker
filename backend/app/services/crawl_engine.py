"""SERP crawl engine with CAPTCHA detection, pause/resume, and screenshot capture."""
import asyncio
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import (
    CAPTCHA_TIMEOUT,
    CRAWL_DELAY_MAX,
    CRAWL_DELAY_MIN,
    SCREENSHOT_DIR,
    USER_AGENT_LIST_PATH,
)
from ..database import async_session
from ..models.models import AioCitation, TrackingJob, TrackingResult, TrackingRun
from .aio_parser import detect_aio, match_citations_to_target, normalize_url
from .serp_parser import parse_organic_results

logger = logging.getLogger(__name__)


class RunManager:
    """Manages active run state and WebSocket broadcasting."""

    _instance = None

    def __init__(self):
        self.active_run_id: str | None = None
        self.abort_requested: bool = False
        self.ws_connections: dict[str, list] = {}  # run_id -> [websocket]

    @classmethod
    def get_instance(cls) -> "RunManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_ws(self, run_id: str, ws):
        self.ws_connections.setdefault(run_id, []).append(ws)

    def unregister_ws(self, run_id: str, ws):
        if run_id in self.ws_connections:
            self.ws_connections[run_id] = [w for w in self.ws_connections[run_id] if w is not ws]

    async def broadcast(self, run_id: str, message: dict):
        if run_id not in self.ws_connections:
            return
        dead = []
        for ws in self.ws_connections[run_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.ws_connections[run_id].remove(ws)

    def request_abort(self):
        self.abort_requested = True


def _load_user_agents() -> list[str]:
    try:
        with open(USER_AGENT_LIST_PATH) as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"]


async def _detect_captcha(page: Page) -> bool:
    """Check if the current page shows a CAPTCHA."""
    url = page.url
    if "/sorry/" in url or "sorry/index" in url:
        return True

    try:
        content = await page.content()
        captcha_signals = ["unusual traffic", "automated queries", "captcha-form"]
        if any(signal in content.lower() for signal in captcha_signals):
            return True
    except Exception:
        pass

    try:
        recaptcha = page.locator("iframe[src*='recaptcha']")
        if await recaptcha.count() > 0:
            return True
    except Exception:
        pass

    # Check if search results are missing (might indicate block)
    try:
        search = page.locator("#search")
        if await search.count() == 0:
            # Could be a CAPTCHA page without obvious markers
            body_text = await page.locator("body").inner_text()
            if len(body_text.strip()) < 200:
                return True
    except Exception:
        pass

    return False


async def _wait_for_captcha_resolution(page: Page, run_id: str, manager: RunManager) -> bool:
    """Wait for user to solve CAPTCHA. Returns True if resolved, False if timed out."""
    start_time = time.time()
    while time.time() - start_time < CAPTCHA_TIMEOUT:
        if manager.abort_requested:
            return False
        await asyncio.sleep(2)
        if not await _detect_captcha(page):
            return True
    return False


async def _take_screenshot(page: Page, path: Path):
    """Take a full-page screenshot and save to path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(path), full_page=True)


async def _crawl_single_job(
    page: Page,
    job: TrackingJob,
    run: TrackingRun,
    db: AsyncSession,
    manager: RunManager,
) -> TrackingResult:
    """Crawl a single tracking job: navigate, parse, screenshot, save."""
    result = TrackingResult(
        job_id=job.id,
        run_id=run.id,
    )
    screenshot_dir = SCREENSHOT_DIR / run.id / job.id

    try:
        # Navigate to page 1
        url = f"https://www.google.com/search?q={job.query}&gl={job.gl}&hl={job.hl}&num=10"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # CAPTCHA check
        if await _detect_captcha(page):
            await manager.broadcast(run.id, {
                "type": "captcha_required",
                "job_id": job.id,
                "message": "CAPTCHA detected — please solve it in the browser window",
            })

            async with async_session() as status_db:
                run_record = await status_db.get(TrackingRun, run.id)
                if run_record:
                    run_record.status = "paused_captcha"
                    await status_db.commit()

            resolved = await _wait_for_captcha_resolution(page, run.id, manager)

            if not resolved:
                result.error = "CAPTCHA timeout - not resolved within time limit"
                db.add(result)
                await db.commit()
                return result

            await manager.broadcast(run.id, {
                "type": "captcha_resolved",
                "message": "CAPTCHA resolved, resuming crawl",
            })

            async with async_session() as status_db:
                run_record = await status_db.get(TrackingRun, run.id)
                if run_record:
                    run_record.status = "running"
                    await status_db.commit()

            # Re-navigate after CAPTCHA
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

        # AIO detection
        aio_data = await detect_aio(page)
        if aio_data:
            result.aio_present = True
            result.aio_content = aio_data["content"]

            # Screenshot AIO
            if aio_data["element"]:
                try:
                    await aio_data["element"].scroll_into_view_if_needed()
                    await _take_screenshot(page, screenshot_dir / "aio.png")
                    result.screenshot_aio_path = str(screenshot_dir / "aio.png")
                except Exception as e:
                    logger.warning("Failed to screenshot AIO: %s", e)

            # Process citations
            is_cited, citation_pos = match_citations_to_target(
                aio_data["citations"], job.target_url
            )
            result.aio_url_cited = is_cited
            result.aio_citation_position = citation_pos

            # Save citation records
            for i, cit in enumerate(aio_data["citations"]):
                aio_cit = AioCitation(
                    result_id=result.id,
                    position=i + 1,
                    cited_url=cit["url"],
                    cited_title=cit.get("title"),
                    is_target=normalize_url(cit["url"]) == normalize_url(job.target_url),
                )
                result.aio_citations.append(aio_cit)

        # Screenshot page 1
        await _take_screenshot(page, screenshot_dir / "page1.png")
        result.screenshot_page1_path = str(screenshot_dir / "page1.png")

        # Parse page 1
        page1_results = await parse_organic_results(page, page_number=1)

        # Navigate to page 2
        page2_url = f"{url}&start=10"
        await page.goto(page2_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # CAPTCHA check page 2
        if await _detect_captcha(page):
            await manager.broadcast(run.id, {
                "type": "captcha_required",
                "job_id": job.id,
                "message": "CAPTCHA detected on page 2 — please solve it in the browser window",
            })
            async with async_session() as status_db:
                run_record = await status_db.get(TrackingRun, run.id)
                if run_record:
                    run_record.status = "paused_captcha"
                    await status_db.commit()

            resolved = await _wait_for_captcha_resolution(page, run.id, manager)
            if resolved:
                await manager.broadcast(run.id, {"type": "captcha_resolved"})
                async with async_session() as status_db:
                    run_record = await status_db.get(TrackingRun, run.id)
                    if run_record:
                        run_record.status = "running"
                        await status_db.commit()
                await page.goto(page2_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

        # Screenshot page 2
        await _take_screenshot(page, screenshot_dir / "page2.png")
        result.screenshot_page2_path = str(screenshot_dir / "page2.png")

        # Parse page 2
        page2_results = await parse_organic_results(page, page_number=2)

        # Combine results and find target
        all_results = page1_results + page2_results
        result.total_organic_results = len(all_results)

        target_normalized = normalize_url(job.target_url)
        for r in all_results:
            if normalize_url(r["url"]) == target_normalized:
                result.organic_position = r["position"]
                result.organic_page = 1 if r["position"] <= 10 else 2
                result.result_url = r["url"]
                result.result_title = r["title"]
                result.result_description = r["description"]
                break

    except Exception as e:
        logger.error("Error crawling job %s: %s", job.id, e)
        result.error = str(e)

    db.add(result)
    await db.commit()
    return result


async def execute_run(run_id: str, job_ids: list[str]):
    """Execute a tracking run: launch browser, crawl all jobs, save results."""
    manager = RunManager.get_instance()
    manager.active_run_id = run_id
    manager.abort_requested = False

    user_agents = _load_user_agents()
    user_agent = random.choice(user_agents)

    async with async_session() as db:
        # Load jobs
        stmt = select(TrackingJob).where(TrackingJob.id.in_(job_ids))
        result = await db.execute(stmt)
        jobs = list(result.scalars().all())

        # Update run with total
        run = await db.get(TrackingRun, run_id)
        if not run:
            return
        run.total_jobs = len(jobs)
        await db.commit()

        await manager.broadcast(run_id, {
            "type": "run_started",
            "run_id": run_id,
            "progress": {"total": len(jobs), "completed": 0, "failed": 0},
        })

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=user_agent,
        )
        page = await context.new_page()

        completed = 0
        failed = 0

        for i, job in enumerate(jobs):
            if manager.abort_requested:
                break

            await manager.broadcast(run_id, {
                "type": "job_started",
                "job_id": job.id,
                "message": f"Crawling: {job.query} (gl={job.gl}, hl={job.hl})",
                "progress": {"total": len(jobs), "completed": completed, "failed": failed, "current": i + 1},
            })

            async with async_session() as db:
                # Re-fetch job in this session
                fresh_job = await db.get(TrackingJob, job.id)
                fresh_run = await db.get(TrackingRun, run_id)
                if not fresh_job or not fresh_run:
                    continue

                crawl_result = await _crawl_single_job(page, fresh_job, fresh_run, db, manager)

                if crawl_result.error:
                    failed += 1
                else:
                    completed += 1

                fresh_run.completed_jobs = completed
                fresh_run.failed_jobs = failed
                await db.commit()

            await manager.broadcast(run_id, {
                "type": "job_completed",
                "job_id": job.id,
                "progress": {"total": len(jobs), "completed": completed, "failed": failed},
                "result": {
                    "position": crawl_result.organic_position,
                    "aio_present": crawl_result.aio_present,
                    "aio_url_cited": crawl_result.aio_url_cited,
                    "error": crawl_result.error,
                },
            })

            # Random delay between jobs
            if i < len(jobs) - 1 and not manager.abort_requested:
                delay = random.uniform(CRAWL_DELAY_MIN, CRAWL_DELAY_MAX)
                await asyncio.sleep(delay)

        await context.close()
        await browser.close()

    # Finalize run
    async with async_session() as db:
        run = await db.get(TrackingRun, run_id)
        if run:
            run.completed_at = datetime.now(timezone.utc)
            run.status = "aborted" if manager.abort_requested else "completed"
            run.completed_jobs = completed
            run.failed_jobs = failed
            await db.commit()

    await manager.broadcast(run_id, {
        "type": "run_completed",
        "run_id": run_id,
        "status": "aborted" if manager.abort_requested else "completed",
        "progress": {"total": len(jobs), "completed": completed, "failed": failed},
    })

    manager.active_run_id = None
