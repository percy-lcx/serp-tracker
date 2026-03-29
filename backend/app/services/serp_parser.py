"""Parse organic search results from Google SERP pages."""
import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)


async def parse_organic_results(page: Page, page_number: int = 1) -> list[dict]:
    """Parse organic search results from a Google SERP page.

    Returns list of dicts with keys: position, url, title, description
    """
    results = []
    offset = (page_number - 1) * 10

    try:
        # Wait for search results container
        await page.wait_for_selector("#search", timeout=10000)
    except Exception:
        logger.warning("Search results container not found on page %d", page_number)
        return results

    # Standard organic result selectors
    result_selectors = [
        "#search .g:not(.g-blk)",
        "#rso .g:not(.g-blk)",
        "#rso > div > div.g",
        "#rso div[data-hveid] .g",
    ]

    elements = None
    for selector in result_selectors:
        locator = page.locator(selector)
        count = await locator.count()
        if count > 0:
            elements = locator
            break

    if elements is None:
        logger.warning("No organic results found on page %d", page_number)
        return results

    count = await elements.count()
    for i in range(min(count, 10)):
        try:
            el = elements.nth(i)

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

            # Extract description
            desc = ""
            for desc_sel in [
                "div[data-sncf] span",
                ".VwiC3b span",
                "div[style='-webkit-line-clamp:2'] span",
                ".IsZvec span",
            ]:
                desc_el = el.locator(desc_sel).first
                if await desc_el.count() > 0:
                    desc = await desc_el.inner_text()
                    if desc.strip():
                        break

            results.append({
                "position": offset + len(results) + 1,
                "url": url,
                "title": title.strip(),
                "description": desc.strip(),
            })
        except Exception as e:
            logger.debug("Error parsing result %d on page %d: %s", i, page_number, e)
            continue

    return results
