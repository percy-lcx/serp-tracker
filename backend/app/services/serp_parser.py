"""Parse organic search results from Google SERP pages."""
import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)


async def _is_serp_feature(el) -> bool:
    """Return True if the element is a known non-organic SERP feature (PAA, Videos, etc.)."""
    try:
        # People Also Ask containers
        if await el.locator("[data-initq]").count() > 0:
            return True
        if await el.locator("related-question-pair").count() > 0:
            return True

        # Check class for block-level features
        class_attr = await el.get_attribute("class") or ""
        if "g-blk" in class_attr:
            return True

        # Video carousel / Top Stories / other sectioned features
        if await el.locator("xpath=ancestor::g-section-with-header").count() > 0:
            return True
    except Exception:
        pass
    return False


async def parse_organic_results(page: Page, page_number: int = 1) -> list[dict]:
    """Parse organic search results from a Google SERP page.

    Returns list of dicts with keys: position, url, title, description
    """
    results = []
    offset = (page_number - 1) * 10

    # Wait for any search results container
    container_found = False
    for container_sel in ["#search", "#rso", "#main"]:
        try:
            await page.wait_for_selector(container_sel, timeout=5000)
            container_found = True
            logger.debug("Container '%s' found on page %d", container_sel, page_number)
            break
        except Exception:
            continue

    if not container_found:
        logger.warning("No search container found on page %d", page_number)

    # Try multiple selector strategies for organic results
    result_selectors = [
        # Standard selectors — exclude feature blocks and PAA containers
        "#rso .g:not(.g-blk):not([data-initq])",
        "#search .g:not(.g-blk):not([data-initq])",
        "#rso > div > div.g",
        "#rso div[data-hveid] .g",
        # Broader fallbacks — modern Google layouts
        "#rso .g",
        "#search .g",
        # Result blocks with data attributes
        "div[data-hveid] div[data-ved] .tF2Cxc",
        # Individual result containers with cite + h3
        "#rso div[data-hveid]:has(h3):has(a[href])",
        "#search div[data-hveid]:has(h3):has(a[href])",
        # Broadest fallback: any div with h3 inside search
        "#rso > div:has(h3 a[href^='http'])",
    ]

    elements = None
    matched_selector = None
    for selector in result_selectors:
        try:
            locator = page.locator(selector)
            count = await locator.count()
            if count > 0:
                elements = locator
                matched_selector = selector
                logger.debug("Organic results matched selector '%s' with %d elements on page %d",
                           selector, count, page_number)
                break
        except Exception:
            continue

    if elements is None:
        logger.warning("No organic results found on page %d with any selector", page_number)
        return results

    count = await elements.count()
    max_results = 10
    max_scan = min(count, 50)
    scanned = 0

    for i in range(max_scan):
        if len(results) >= max_results:
            break
        scanned = i + 1
        try:
            el = elements.nth(i)

            # Skip known SERP features (PAA, Videos, etc.)
            if await _is_serp_feature(el):
                logger.debug("Skipping SERP feature element at index %d on page %d", i, page_number)
                continue

            # Extract URL
            link = el.locator("a[href]").first
            if await link.count() == 0:
                continue
            url = await link.get_attribute("href")
            if not url or not url.startswith("http"):
                continue

            # Extract title
            title_el = el.locator("h3").first
            title = await title_el.inner_text() if await title_el.count() > 0 else ""

            # Skip if no title (likely not a real organic result)
            if not title.strip():
                continue

            # Extract description
            desc = ""
            for desc_sel in [
                "div[data-sncf] span",
                ".VwiC3b span",
                ".VwiC3b",
                "div[style='-webkit-line-clamp:2'] span",
                ".IsZvec span",
                "div[data-sncf]",
                # Broader fallback
                "span:not(h3 span)",
            ]:
                try:
                    desc_el = el.locator(desc_sel).first
                    if await desc_el.count() > 0:
                        desc = await desc_el.inner_text()
                        if desc.strip() and desc.strip() != title.strip():
                            break
                        desc = ""
                except Exception:
                    continue

            results.append({
                "position": offset + len(results) + 1,
                "url": url,
                "title": title.strip(),
                "description": desc.strip(),
            })
        except Exception as e:
            logger.debug("Error parsing result %d on page %d: %s", i, page_number, e)
            continue

    logger.info("Parsed %d organic results from %d candidates (scanned %d) on page %d (selector: %s)",
                len(results), count, scanned, page_number, matched_selector)
    return results
