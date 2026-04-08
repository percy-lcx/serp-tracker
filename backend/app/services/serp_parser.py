"""Parse organic search results from Google SERP pages."""
import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)

_JS_EXTRACT_ORGANIC = """
() => {
    const container = document.querySelector('#rso') || document.querySelector('#search');
    if (!container) return [];

    const featureSelectors = [
        'g-section-with-header',
        '[data-initq]',
        '[data-md]',
        '.kp-blk',
        'g-accordion-expander',
        '[data-attrid]',
        'related-question-pair',
        '[jscontroller][data-initq]',
    ];

    const h3s = container.querySelectorAll('h3');
    const results = [];
    const seenUrls = new Set();

    for (const h3 of h3s) {
        if (results.length >= 10) break;

        // Skip h3 inside SERP feature containers
        let insideFeature = false;
        for (const sel of featureSelectors) {
            if (h3.closest(sel)) {
                insideFeature = true;
                break;
            }
        }
        if (insideFeature) continue;

        // Find the associated link
        let link = null;
        // Check if h3 is inside an anchor
        const parentAnchor = h3.closest('a[href]');
        if (parentAnchor && parentAnchor.href.startsWith('http')) {
            link = parentAnchor;
        }
        // Walk up to find a sibling or ancestor link
        if (!link) {
            let node = h3.parentElement;
            for (let i = 0; i < 6 && node; i++) {
                const a = node.querySelector('a[href^="http"]');
                if (a && !a.href.startsWith('https://www.google.') &&
                    !a.href.startsWith('https://google.') &&
                    !a.href.startsWith('https://support.google.') &&
                    !a.href.startsWith('https://maps.google.')) {
                    link = a;
                    break;
                }
                node = node.parentElement;
            }
        }

        if (!link) continue;
        const url = link.href;
        if (!url || !url.startsWith('http')) continue;
        if (url.startsWith('https://www.google.') || url.startsWith('https://google.')) continue;
        if (seenUrls.has(url)) continue;
        seenUrls.add(url);

        const title = h3.innerText ? h3.innerText.trim() : '';
        if (!title) continue;

        // Find description: walk up to the result container and look for description elements
        let desc = '';
        let resultBlock = h3;
        for (let i = 0; i < 8; i++) {
            if (!resultBlock.parentElement) break;
            resultBlock = resultBlock.parentElement;
            // Stop at a reasonable container boundary
            if (resultBlock.getAttribute('data-hveid') || resultBlock.classList.contains('g')) break;
        }
        const descSelectors = ['.VwiC3b', '[data-sncf]', '.IsZvec', "div[style*='-webkit-line-clamp']"];
        for (const dSel of descSelectors) {
            const dEl = resultBlock.querySelector(dSel);
            if (dEl) {
                const txt = dEl.innerText ? dEl.innerText.trim() : '';
                if (txt && txt !== title) {
                    desc = txt;
                    break;
                }
            }
        }

        results.push({ url, title, description: desc });
    }
    return results;
}
"""


async def _parse_organic_via_js(page) -> list[dict]:
    """Extract organic results using in-browser JS evaluation."""
    try:
        raw = await page.evaluate(_JS_EXTRACT_ORGANIC)
        if isinstance(raw, list):
            return raw
    except Exception as e:
        logger.debug("JS organic extraction failed: %s", e)
    return []


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

    # Primary approach: JS evaluation for robust organic result extraction
    js_raw = await _parse_organic_via_js(page)
    if len(js_raw) >= 3:
        for item in js_raw:
            results.append({
                "position": offset + len(results) + 1,
                "url": item.get("url", ""),
                "title": item.get("title", "").strip(),
                "description": item.get("description", "").strip(),
            })
        logger.info("Parsed %d organic results via JS evaluation on page %d", len(results), page_number)
        return results

    logger.debug("JS evaluation returned %d results on page %d, falling back to CSS selectors",
                 len(js_raw), page_number)

    # Fallback: Try multiple selector strategies for organic results
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
