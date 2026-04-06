"""AI Overview detection, content extraction, and citation parsing."""
import json
import logging
from pathlib import Path
from urllib.parse import urlparse

from typing import Optional, Tuple, List

from playwright.async_api import Page

from ..config import AIO_SELECTORS_PATH

logger = logging.getLogger(__name__)


def load_selectors() -> dict:
    path = Path(AIO_SELECTORS_PATH)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    logger.warning("AIO selectors config not found at %s, using defaults", path)
    return {
        "aio_container_selectors": ["div.wDYxhc[data-md]"],
        "aio_citation_selectors": ["div.wDYxhc a[href]"],
        "aio_content_selectors": ["div.wDYxhc[data-md] span"],
    }


def normalize_url(url: str) -> str:
    """Normalize URL for comparison: strip protocol, www, trailing slash, query params."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/")
    return f"{host}{path}".lower()


async def detect_aio(page: Page) -> Optional[dict]:
    """Detect and extract AI Overview content and citations from a SERP page.

    Returns dict with keys: content, citations, element (for screenshot) or None if no AIO.
    """
    selectors = load_selectors()

    aio_element = None
    for selector in selectors["aio_container_selectors"]:
        try:
            el = page.locator(selector).first
            if await el.count() > 0 and await el.is_visible():
                aio_element = el
                logger.info("AIO detected with selector: %s", selector)
                break
        except Exception:
            continue

    if aio_element is None:
        return None

    # Extract content
    content = ""
    for selector in selectors["aio_content_selectors"]:
        try:
            content_el = aio_element.locator(selector).first
            if await content_el.count() > 0:
                content = await content_el.inner_text()
                if content.strip():
                    break
        except Exception:
            continue

    if not content.strip():
        try:
            content = await aio_element.inner_text()
        except Exception:
            content = ""

    # Extract citations
    citations = []
    for selector in selectors["aio_citation_selectors"]:
        try:
            links = aio_element.locator(selector)
            count = await links.count()
            if count > 0:
                for i in range(count):
                    link = links.nth(i)
                    href = await link.get_attribute("href")
                    title = await link.inner_text()
                    if href and href.startswith("http") and "google.com" not in href:
                        citations.append({
                            "url": href,
                            "title": title.strip() if title else None,
                        })
                if citations:
                    break
        except Exception:
            continue

    # Deduplicate citations by URL
    seen = set()
    unique_citations = []
    for c in citations:
        normalized = normalize_url(c["url"])
        if normalized not in seen:
            seen.add(normalized)
            unique_citations.append(c)

    return {
        "content": content.strip(),
        "citations": unique_citations,
        "element": aio_element,
    }


def match_citations_to_target(citations: List[dict], target_url: str) -> Tuple[bool, Optional[int]]:
    """Check if target URL appears in citations. Returns (is_cited, position)."""
    target_normalized = normalize_url(target_url)
    for i, citation in enumerate(citations):
        if normalize_url(citation["url"]) == target_normalized:
            return True, i + 1
    return False, None
