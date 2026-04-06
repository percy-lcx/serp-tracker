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


async def _find_aio_by_text(page: Page) -> Optional[object]:
    """Fallback AIO detection: find container by looking for 'AI Overview' header text."""
    try:
        # Look for elements that contain the exact text "AI Overview"
        header = page.get_by_text("AI Overview", exact=True).first
        if await header.count() == 0:
            return None

        # Walk up to find a meaningful container parent
        # The AIO section is typically a large container div wrapping the header + content
        # Try getting progressively larger parent containers
        for ancestor_sel in [
            "xpath=./ancestor::div[contains(@class, 'M8OgIe')]",
            "xpath=./ancestor::div[contains(@class, 'wDYxhc')]",
            "xpath=./ancestor::div[contains(@class, 'Wt5Tfe')]",
            "xpath=./ancestor::div[@data-md]",
            "xpath=./ancestor::div[@jscontroller]",
        ]:
            try:
                ancestor = header.locator(ancestor_sel).last
                if await ancestor.count() > 0:
                    # Verify it's a substantial container (not just a tiny wrapper)
                    box = await ancestor.bounding_box()
                    if box and box["height"] > 100:
                        return ancestor
            except Exception:
                continue

        # Last resort: grab the direct parent's parent chain up 3 levels
        current = header
        for _ in range(5):
            try:
                current = current.locator("xpath=./parent::div").first
                if await current.count() == 0:
                    break
                box = await current.bounding_box()
                if box and box["height"] > 200 and box["width"] > 400:
                    return current
            except Exception:
                break

    except Exception as e:
        logger.debug("Text-based AIO detection failed: %s", e)

    return None


async def detect_aio(page: Page) -> dict:
    """Detect and extract AI Overview content and citations from a SERP page.

    Always returns a dict with keys: content, citations, element, debug.
    element is None if no AIO was found.
    """
    selectors = load_selectors()
    debug = {
        "selectors_tried": 0,
        "matched_selector": None,
        "content_length": 0,
        "citation_selector_matched": None,
        "citation_fallback_used": False,
        "citations_found": 0,
        "selector_errors": [],
        "detection_method": None,
    }

    no_aio = {"content": "", "citations": [], "element": None, "debug": debug}

    # Phase 1: Try CSS selectors from config
    aio_element = None
    for selector in selectors["aio_container_selectors"]:
        debug["selectors_tried"] += 1
        try:
            el = page.locator(selector).first
            count = await el.count()
            if count > 0 and await el.is_visible():
                aio_element = el
                debug["matched_selector"] = selector
                debug["detection_method"] = "css_selector"
                logger.info("AIO detected with selector: %s", selector)
                break
            else:
                logger.debug("AIO selector '%s': count=%d", selector, count)
        except Exception as e:
            debug["selector_errors"].append(f"{selector}: {e}")
            continue

    # Phase 2: Text-based fallback — look for "AI Overview" header text
    if aio_element is None:
        logger.info("CSS selectors failed, trying text-based AIO detection")
        aio_element = await _find_aio_by_text(page)
        if aio_element is not None:
            debug["matched_selector"] = "text:'AI Overview' (ancestor walk)"
            debug["detection_method"] = "text_fallback"
            logger.info("AIO detected via text-based fallback")

    if aio_element is None:
        logger.info("AIO not found after CSS selectors + text fallback")
        return no_aio

    # Extract content from AIO element
    content = ""
    try:
        content = await aio_element.inner_text()
    except Exception as e:
        logger.warning("Failed to extract AIO content: %s", e)
        content = ""
    debug["content_length"] = len(content.strip())

    # Extract citations
    citations = []

    # Try specific selectors scoped within the AIO element
    for selector in selectors["aio_citation_selectors"]:
        try:
            links = aio_element.locator(selector)
            count = await links.count()
            scope = "element"
            if count == 0:
                links = page.locator(selector)
                count = await links.count()
                scope = "page"
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
                    debug["citation_selector_matched"] = f"{selector} ({scope}-scoped, {count} links)"
                    break
        except Exception:
            continue

    # Fallback: find all links within the AIO element generically
    if not citations:
        debug["citation_fallback_used"] = True
        try:
            links = aio_element.locator("a[href]")
            count = await links.count()
            for i in range(count):
                link = links.nth(i)
                href = await link.get_attribute("href")
                title = await link.inner_text()
                if href and href.startswith("http") and "google.com" not in href:
                    citations.append({
                        "url": href,
                        "title": title.strip() if title else None,
                    })
        except Exception:
            pass

    # Deduplicate citations by URL
    seen = set()
    unique_citations = []
    for c in citations:
        normalized = normalize_url(c["url"])
        if normalized not in seen:
            seen.add(normalized)
            unique_citations.append(c)

    debug["citations_found"] = len(unique_citations)

    return {
        "content": content.strip(),
        "citations": unique_citations,
        "element": aio_element,
        "debug": debug,
    }


def match_citations_to_target(citations: List[dict], target_url: str) -> Tuple[bool, Optional[int]]:
    """Check if target URL appears in citations. Returns (is_cited, position)."""
    target_normalized = normalize_url(target_url)
    for i, citation in enumerate(citations):
        if normalize_url(citation["url"]) == target_normalized:
            return True, i + 1
    return False, None
