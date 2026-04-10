"""AI Overview detection, content extraction, and citation parsing."""
import json
import logging
from pathlib import Path
from urllib.parse import urlparse

from typing import Optional, Tuple, List

from playwright.async_api import Page

from ..config import AIO_SELECTORS_PATH, AIO_DEBUG_DUMP

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
        "aio_card_citation_selectors": [],
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


async def _click_expand_button(page: Page, search_scopes: list, css_selectors: list, button_texts: list) -> Optional[str]:
    """Try to find and click an expand button using CSS selectors and text matching.

    Searches the provided scopes first, then falls back to a page-level text search
    with bounding-box proximity to the AIO element.

    Returns the matched selector description, or None if no button was found.
    """
    # Phase 1: Search within provided scopes (AIO element, parent, ancestor)
    for scope_name, scope_el in search_scopes:
        # Try CSS selectors
        for selector in css_selectors:
            try:
                btn = scope_el.locator(selector).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(1000)
                    return f"{selector} ({scope_name})"
            except Exception:
                continue

        # Try text-based detection
        for text in button_texts:
            try:
                btn = scope_el.get_by_text(text, exact=True).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(1000)
                    return f"text:'{text}' ({scope_name})"
            except Exception:
                continue

    # Phase 2: Page-level text search with proximity to AIO
    # The button may be a sibling/cousin of the AIO element, outside all scopes
    aio_box = None
    if search_scopes:
        try:
            aio_box = await search_scopes[0][1].bounding_box()
        except Exception:
            pass

    for text in button_texts:
        try:
            # get_by_role("button") won't work since these are often divs/links
            candidates = page.get_by_text(text, exact=True)
            count = await candidates.count()
            for i in range(count):
                btn = candidates.nth(i)
                if not await btn.is_visible():
                    continue
                # If we have a bounding box, verify proximity to AIO
                if aio_box:
                    btn_box = await btn.bounding_box()
                    if btn_box:
                        # Button should be near the AIO horizontally and below or within it
                        x_near = abs(btn_box["x"] - aio_box["x"]) < aio_box["width"] + 100
                        y_near = btn_box["y"] <= aio_box["y"] + aio_box["height"] + 200
                        y_not_far_above = btn_box["y"] >= aio_box["y"] - 50
                        if not (x_near and y_near and y_not_far_above):
                            continue
                await btn.click()
                await page.wait_for_timeout(1000)
                return f"text:'{text}' (page-level)"
        except Exception:
            continue

    return None


async def _expand_aio(page: Page, aio_element, selectors: dict) -> dict:
    """Click 'Show more' and 'Show all' buttons to fully expand the AIO content and cards.

    Google's AI Overview often truncates the main text behind a 'Show more' button
    and hides additional right-side card citations behind a 'Show all' button.
    This function clicks both to reveal all content before extraction.

    Returns a debug dict with what was expanded.
    """
    expand_debug = {
        "show_more_clicked": False,
        "show_more_selector": None,
        "show_all_clicked": False,
        "show_all_selector": None,
    }

    # Build search scopes from narrowest to broadest
    search_scopes = [("aio_element", aio_element)]
    try:
        parent = aio_element.locator("xpath=./parent::div").first
        if await parent.count() > 0:
            search_scopes.append(("parent", parent))
    except Exception:
        pass
    try:
        ancestor = aio_element.locator("xpath=./ancestor::div[@jscontroller]").last
        if await ancestor.count() > 0:
            search_scopes.append(("ancestor", ancestor))
    except Exception:
        pass

    # --- Click "Show more" to expand the AIO text ---
    show_more_result = await _click_expand_button(
        page, search_scopes,
        css_selectors=selectors.get("aio_expand_button_selectors", []),
        button_texts=["Show more", "Show More"],
    )
    if show_more_result:
        expand_debug["show_more_clicked"] = True
        expand_debug["show_more_selector"] = show_more_result
        logger.info("AIO 'Show more' clicked via %s", show_more_result)

    # --- Click "Show all" to expand the right-side card list ---
    show_all_result = await _click_expand_button(
        page, search_scopes,
        css_selectors=selectors.get("aio_show_all_button_selectors", []),
        button_texts=["Show all", "Show All"],
    )
    if show_all_result:
        expand_debug["show_all_clicked"] = True
        expand_debug["show_all_selector"] = show_all_result
        logger.info("AIO 'Show all' clicked via %s", show_all_result)

    return expand_debug


async def _dump_aio_region_html(page: Page, aio_element) -> Optional[str]:
    """Capture HTML of the broader AIO region for selector development.

    Only runs when AIO_DEBUG_DUMP is enabled. Walks up from the AIO element
    to a broader parent and dumps its inner HTML.
    """
    if not AIO_DEBUG_DUMP:
        return None

    try:
        # Try to get a broader parent that encompasses both AIO text and side cards
        for ancestor_sel in [
            "xpath=./ancestor::div[@jscontroller]",
            "xpath=./ancestor::div[contains(@class, 'M8OgIe')]",
            "xpath=./ancestor::div[@data-md]",
        ]:
            try:
                ancestor = aio_element.locator(ancestor_sel).last
                if await ancestor.count() > 0:
                    html = await ancestor.inner_html()
                    logger.info(
                        "AIO region HTML dump (%s, %d chars):\n%s",
                        ancestor_sel, len(html), html[:5000],
                    )
                    return html
            except Exception:
                continue

        # Fallback: walk up 3 parent levels
        current = aio_element
        for _ in range(3):
            try:
                current = current.locator("xpath=./parent::div").first
                if await current.count() == 0:
                    break
            except Exception:
                break

        html = await current.inner_html()
        logger.info("AIO region HTML dump (parent walk, %d chars):\n%s", len(html), html[:5000])
        return html
    except Exception as e:
        logger.debug("AIO region HTML dump failed: %s", e)
        return None


async def _extract_inline_citations(aio_element, page: Page, selectors: dict) -> Tuple[List[dict], dict]:
    """Extract inline citations from within the AIO text content.

    Returns (citations, debug_info) where each citation has a 'type' key set to 'inline'.
    """
    citations = []
    debug_info = {
        "citation_selector_matched": None,
        "citation_fallback_used": False,
    }

    # Try specific selectors scoped within the AIO element only
    for selector in selectors.get("aio_citation_selectors", []):
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
                            "type": "inline",
                        })
                if citations:
                    debug_info["citation_selector_matched"] = f"{selector} (element-scoped, {count} links)"
                    break
        except Exception:
            continue

    # Fallback: find all links within the AIO element generically
    if not citations:
        debug_info["citation_fallback_used"] = True
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
                        "type": "inline",
                    })
        except Exception:
            pass

    return citations, debug_info


async def _extract_card_citations(aio_element, page: Page, selectors: dict) -> Tuple[List[dict], dict]:
    """Extract right-side card citations from the AIO region.

    These are thumbnail/preview cards displayed alongside the AIO text.
    Searches progressively broader scopes since cards may be siblings of the AIO element.
    Returns (citations, debug_info) where each citation has a 'type' key set to 'card'.
    """
    card_selectors = selectors.get("aio_card_citation_selectors", [])
    if not card_selectors:
        return [], {"card_citation_selector_matched": None, "card_citations_found": 0}

    citations = []
    debug_info = {
        "card_citation_selector_matched": None,
        "card_citations_found": 0,
    }

    # Build a list of scopes to search, from narrowest to broadest
    scopes = []

    # Scope 1: Within the AIO element itself
    scopes.append(("aio_element", aio_element))

    # Scope 2: Parent of the AIO element (cards may be siblings)
    try:
        parent = aio_element.locator("xpath=./parent::div").first
        if await parent.count() > 0:
            scopes.append(("parent", parent))
    except Exception:
        pass

    # Scope 3: Broader ancestor with jscontroller (likely the full AIO widget)
    try:
        ancestor = aio_element.locator("xpath=./ancestor::div[@jscontroller]").last
        if await ancestor.count() > 0:
            scopes.append(("jscontroller_ancestor", ancestor))
    except Exception:
        pass

    for scope_name, scope_el in scopes:
        for selector in card_selectors:
            try:
                links = scope_el.locator(selector)
                count = await links.count()
                if count == 0:
                    continue
                for i in range(count):
                    link = links.nth(i)
                    href = await link.get_attribute("href")
                    title = await link.inner_text()
                    if href and href.startswith("http") and "google.com" not in href:
                        citations.append({
                            "url": href,
                            "title": title.strip() if title else None,
                            "type": "card",
                        })
                if citations:
                    debug_info["card_citation_selector_matched"] = (
                        f"{selector} ({scope_name}-scoped, {count} links)"
                    )
                    debug_info["card_citations_found"] = len(citations)
                    return citations, debug_info
            except Exception:
                continue

    # Final fallback: page-level search with bounding-box proximity check
    aio_box = None
    try:
        aio_box = await aio_element.bounding_box()
    except Exception:
        pass

    if aio_box:
        for selector in card_selectors:
            try:
                links = page.locator(selector)
                count = await links.count()
                if count == 0:
                    continue
                for i in range(count):
                    link = links.nth(i)
                    link_box = await link.bounding_box()
                    if not link_box:
                        continue
                    # Accept links that are near the AIO element:
                    # horizontally within 50px left or to the right,
                    # vertically within the AIO height + 100px margin
                    x_near = link_box["x"] >= aio_box["x"] - 50
                    y_near = link_box["y"] <= aio_box["y"] + aio_box["height"] + 100
                    y_not_above = link_box["y"] >= aio_box["y"] - 50
                    if x_near and y_near and y_not_above:
                        href = await link.get_attribute("href")
                        title = await link.inner_text()
                        if href and href.startswith("http") and "google.com" not in href:
                            citations.append({
                                "url": href,
                                "title": title.strip() if title else None,
                                "type": "card",
                            })
                if citations:
                    debug_info["card_citation_selector_matched"] = (
                        f"{selector} (page-scoped+proximity, {count} links)"
                    )
                    break
            except Exception:
                continue

    debug_info["card_citations_found"] = len(citations)
    return citations, debug_info


def _merge_and_deduplicate(inline_citations: List[dict], card_citations: List[dict]) -> List[dict]:
    """Merge inline and card citations, deduplicating by normalized URL.

    If a URL appears in both inline and card lists, it is kept once with type 'inline+card'.
    Inline citations come first, preserving their original order.
    """
    seen = {}  # normalized_url -> index in result list
    result = []

    for c in inline_citations:
        normalized = normalize_url(c["url"])
        if normalized not in seen:
            seen[normalized] = len(result)
            result.append(c)

    for c in card_citations:
        normalized = normalize_url(c["url"])
        if normalized in seen:
            # URL already exists from inline — upgrade type to inline+card
            idx = seen[normalized]
            result[idx]["type"] = "inline+card"
        else:
            seen[normalized] = len(result)
            result.append(c)

    return result


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
        "card_citation_selector_matched": None,
        "card_citations_found": 0,
        "show_more_clicked": False,
        "show_all_clicked": False,
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

    # Expand the AIO: click "Show more" and "Show all" to reveal full content and cards
    expand_debug = await _expand_aio(page, aio_element, selectors)
    debug["show_more_clicked"] = expand_debug["show_more_clicked"]
    debug["show_all_clicked"] = expand_debug["show_all_clicked"]
    if expand_debug.get("show_more_selector"):
        debug["show_more_selector"] = expand_debug["show_more_selector"]
    if expand_debug.get("show_all_selector"):
        debug["show_all_selector"] = expand_debug["show_all_selector"]

    # Optional: dump broader AIO region HTML for selector development
    await _dump_aio_region_html(page, aio_element)

    # Extract content from AIO element
    content = ""
    try:
        content = await aio_element.inner_text()
    except Exception as e:
        logger.warning("Failed to extract AIO content: %s", e)
        content = ""
    debug["content_length"] = len(content.strip())

    # Extract inline citations (links within the AIO text)
    inline_citations, inline_debug = await _extract_inline_citations(aio_element, page, selectors)
    debug["citation_selector_matched"] = inline_debug["citation_selector_matched"]
    debug["citation_fallback_used"] = inline_debug["citation_fallback_used"]

    # Extract right-side card citations (thumbnail/preview cards)
    card_citations, card_debug = await _extract_card_citations(aio_element, page, selectors)
    debug["card_citation_selector_matched"] = card_debug["card_citation_selector_matched"]
    debug["card_citations_found"] = card_debug["card_citations_found"]

    # Merge and deduplicate
    unique_citations = _merge_and_deduplicate(inline_citations, card_citations)
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
