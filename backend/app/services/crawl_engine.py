"""SERP crawl engine with CAPTCHA detection, pause/resume, and screenshot capture."""
import asyncio
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright, BrowserContext, Page
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import (
    BROWSER_DATA_DIR,
    CAPTCHA_TIMEOUT,
    CRAWL_DELAY_MAX,
    CRAWL_DELAY_MIN,
    HEADLESS,
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
        self.active_run_id = None  # type: Optional[str]
        self.abort_requested = False
        self.ws_connections = {}  # run_id -> [websocket]

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


class BrowserManager:
    """Manages browser lifecycle with persistent context and headless/headed switching."""

    def __init__(self, playwright, user_agent: str):
        self._playwright = playwright
        self._user_agent = user_agent
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._headless: bool = True

    @property
    def page(self) -> Page:
        assert self._page is not None, "Browser not started"
        return self._page

    @property
    def is_headless(self) -> bool:
        return self._headless

    async def start(self, headless: bool = True):
        """Launch a persistent browser context."""
        self._headless = headless
        BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Remove stale lock file from crashed processes
        lock_file = BROWSER_DATA_DIR / "SingletonLock"
        if lock_file.exists():
            try:
                lock_file.unlink()
            except OSError:
                pass

        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=headless,
            viewport={"width": 1920, "height": 1080},
            user_agent=self._user_agent,
        )
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()

    async def restart_headed(self):
        """Close current context and reopen in headed mode. Cookies persist via the data dir."""
        await self._close()
        await self.start(headless=False)

    async def _close(self):
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
            self._page = None

    async def close(self):
        await self._close()


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


async def _handle_captcha(
    browser_mgr: BrowserManager,
    url: str,
    run_id: str,
    job_id: str,
    manager: RunManager,
    debug_fn,
) -> tuple[Page, bool]:
    """Handle CAPTCHA: switch to headed mode if needed, wait for resolution.

    Returns (page, resolved). The page may be a new reference if browser was restarted.
    """
    await manager.broadcast(run_id, {
        "type": "captcha_required",
        "job_id": job_id,
        "message": "CAPTCHA detected — please solve it in the browser window",
    })

    async with async_session() as status_db:
        run_record = await status_db.get(TrackingRun, run_id)
        if run_record:
            run_record.status = "paused_captcha"
            await status_db.commit()

    # Switch to headed if currently headless
    if browser_mgr.is_headless:
        await debug_fn("CAPTCHA in headless mode — restarting browser in headed mode")
        await browser_mgr.restart_headed()
        page = browser_mgr.page
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
    else:
        page = browser_mgr.page

    resolved = await _wait_for_captcha_resolution(page, run_id, manager)

    if resolved:
        await debug_fn("CAPTCHA resolved")
        await manager.broadcast(run_id, {
            "type": "captcha_resolved",
            "message": "CAPTCHA resolved, resuming crawl",
        })
        async with async_session() as status_db:
            run_record = await status_db.get(TrackingRun, run_id)
            if run_record:
                run_record.status = "running"
                await status_db.commit()
    else:
        await debug_fn("CAPTCHA timeout — not resolved within time limit")

    return page, resolved


async def _take_screenshot(page: Page, path: Path):
    """Take a full-page screenshot and save to path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(path), full_page=True)


async def _crawl_single_job(
    browser_mgr: BrowserManager,
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
    debug_lines = []

    async def _debug(msg: str):
        logger.info("[job:%s] %s", job.id[:8], msg)
        debug_lines.append(msg)
        await manager.broadcast(run.id, {"type": "debug_log", "job_id": job.id, "message": msg})

    try:
        page = browser_mgr.page

        # Navigate to page 1
        url = f"https://www.google.com/search?q={job.query}&gl={job.gl}&hl={job.hl}&num=10"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        await _debug(f"Navigated to Google SERP: q={job.query}")

        # CAPTCHA check
        captcha_detected = await _detect_captcha(page)
        await _debug(f"CAPTCHA check: {'DETECTED' if captcha_detected else 'clear'}")
        if captcha_detected:
            page, resolved = await _handle_captcha(
                browser_mgr, url, run.id, job.id, manager, _debug
            )
            if not resolved:
                result.error = "CAPTCHA timeout - not resolved within time limit"
                result.debug_log = "\n".join(debug_lines)
                db.add(result)
                await db.commit()
                return result

            # Re-navigate after CAPTCHA
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            await _debug("Re-navigated after CAPTCHA resolution")

        # Page structure diagnostics
        diag_parts = []
        for sel in ["#search", "#rso", "#main", ".g", "h3"]:
            try:
                cnt = await page.locator(sel).count()
                if cnt > 0:
                    diag_parts.append(f"{sel}={cnt}")
            except Exception:
                pass
        await _debug(f"Page structure: {', '.join(diag_parts) or 'no known containers found'}")

        # AIO detection
        aio_data = await detect_aio(page)
        aio_debug = aio_data.get("debug", {})

        if aio_data["element"]:
            method = aio_debug.get("detection_method", "unknown")
            await _debug(
                f"AIO detected ({method}) — selector: {aio_debug.get('matched_selector', '?')}, "
                f"content: {aio_debug.get('content_length', 0)} chars, "
                f"citations: {aio_debug.get('citations_found', 0)}"
            )
            if aio_debug.get("citation_selector_matched"):
                await _debug(f"AIO citations matched via: {aio_debug['citation_selector_matched']}")
            elif aio_debug.get("citation_fallback_used"):
                await _debug("AIO citations: used generic a[href] fallback")

            result.aio_present = True
            result.aio_content = aio_data["content"]

            # Screenshot AIO element
            aio_screenshot_path = screenshot_dir / "aio.png"
            aio_screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                await aio_data["element"].screenshot(path=str(aio_screenshot_path))
                result.screenshot_aio_path = str(aio_screenshot_path)
                await _debug(f"AIO screenshot saved: {aio_screenshot_path}")
            except Exception as e1:
                await _debug(f"AIO element screenshot failed: {e1} — trying full-page fallback")
                try:
                    await aio_data["element"].scroll_into_view_if_needed()
                    await page.screenshot(path=str(aio_screenshot_path), full_page=True)
                    result.screenshot_aio_path = str(aio_screenshot_path)
                    await _debug(f"AIO screenshot (full-page fallback) saved: {aio_screenshot_path}")
                except Exception as e2:
                    await _debug(f"AIO screenshot fallback also failed: {e2}")
                    logger.warning("Failed to screenshot AIO: %s", e2)

            # Process citations
            is_cited, citation_pos = match_citations_to_target(
                aio_data["citations"], job.target_url
            )
            result.aio_url_cited = is_cited
            result.aio_citation_position = citation_pos
            if is_cited and citation_pos is not None:
                # Store the actual cited URL for debugging
                target_norm = normalize_url(job.target_url)
                for cit in aio_data["citations"]:
                    if normalize_url(cit["url"]) == target_norm:
                        result.aio_citation_url = cit["url"]
                        break
            await _debug(f"AIO target match: cited={is_cited}, citation_position={citation_pos}, url={result.aio_citation_url}")

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
        else:
            errors = aio_debug.get("selector_errors", [])
            error_info = f", errors: {errors}" if errors else ""
            await _debug(
                f"AIO not detected — tried {aio_debug.get('selectors_tried', 0)} selectors{error_info}"
            )

        # Screenshot page 1
        await _take_screenshot(page, screenshot_dir / "page1.png")
        result.screenshot_page1_path = str(screenshot_dir / "page1.png")
        await _debug(f"Page 1 screenshot saved: {screenshot_dir / 'page1.png'}")

        # Parse page 1
        page1_results = await parse_organic_results(page, page_number=1)
        await _debug(f"Page 1 parsed: {len(page1_results)} organic results")

        # Navigate to page 2
        page2_url = f"{url}&start=10"
        await page.goto(page2_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        await _debug("Navigated to page 2")

        # CAPTCHA check page 2
        captcha_p2 = await _detect_captcha(page)
        if captcha_p2:
            await _debug("CAPTCHA detected on page 2")
            page, resolved = await _handle_captcha(
                browser_mgr, page2_url, run.id, job.id, manager, _debug
            )
            if resolved:
                await page.goto(page2_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

        # Screenshot page 2
        await _take_screenshot(page, screenshot_dir / "page2.png")
        result.screenshot_page2_path = str(screenshot_dir / "page2.png")
        await _debug(f"Page 2 screenshot saved: {screenshot_dir / 'page2.png'}")

        # Parse page 2
        page2_results = await parse_organic_results(page, page_number=2)
        await _debug(f"Page 2 parsed: {len(page2_results)} organic results")

        # Combine results and find target
        all_results = page1_results + page2_results
        result.total_organic_results = len(all_results)

        target_normalized = normalize_url(job.target_url)
        found = False
        for r in all_results:
            if normalize_url(r["url"]) == target_normalized:
                result.organic_position = r["position"]
                result.organic_page = 1 if r["position"] <= 10 else 2
                result.result_url = r["url"]
                result.result_title = r["title"]
                result.result_description = r["description"]
                found = True
                break

        if found:
            await _debug(f"Target found: position={result.organic_position}, page={result.organic_page}")
        else:
            await _debug(f"Target URL not found in {len(all_results)} results (target: {job.target_url})")

    except Exception as e:
        logger.error("Error crawling job %s: %s", job.id, e)
        result.error = str(e)
        try:
            await _debug(f"Job error: {e}")
        except Exception:
            pass

    result.debug_log = "\n".join(debug_lines)
    db.add(result)
    await db.commit()
    return result


async def execute_run(run_id: str, job_ids: list[str]):
    """Execute a tracking run: launch browser, crawl all jobs, save results."""
    manager = RunManager.get_instance()
    manager.active_run_id = run_id
    manager.abort_requested = False

    try:
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
            browser_mgr = BrowserManager(p, user_agent)
            await browser_mgr.start(headless=HEADLESS)

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

                    crawl_result = await _crawl_single_job(browser_mgr, fresh_job, fresh_run, db, manager)

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

            await browser_mgr.close()

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

    except Exception:
        logger.exception("execute_run failed for run_id=%s", run_id)

        # Mark run as failed in DB
        try:
            async with async_session() as db:
                run = await db.get(TrackingRun, run_id)
                if run:
                    run.status = "failed"
                    run.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            logger.exception("Failed to mark run %s as failed in DB", run_id)

        # Notify connected WebSocket clients
        try:
            await manager.broadcast(run_id, {
                "type": "run_failed",
                "run_id": run_id,
                "error": "Run failed unexpectedly. Check server logs.",
            })
        except Exception:
            logger.exception("Failed to broadcast failure for run %s", run_id)

    finally:
        manager.active_run_id = None
