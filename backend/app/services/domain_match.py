"""Domain-matching helpers for site profiles.

A "same-domain hit" is any SERP URL that belongs to the same registered domain
(eTLD+1, e.g. example.com) as the tracked URL. The site profile decides whether
subdomain variants (e.g. de.example.com) count as the same site.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

import tldextract

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import SiteProfile

# Disable network fetch — use the bundled snapshot. Avoids first-use latency
# and keeps the tool runnable in offline / sandboxed environments.
_extractor = tldextract.TLDExtract(suffix_list_urls=())


def registered_domain(url: str) -> str:
    """Return the eTLD+1 for a URL (e.g. 'example.com'), or '' if undetectable."""
    if not url:
        return ""
    ext = _extractor(url)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}".lower()
    # IP literals or hosts with no public suffix — fall back to the bare host.
    return (ext.domain or urlparse(url).hostname or "").lower()


def host(url: str) -> str:
    """Return the full lowercase host (with subdomains) or '' if missing."""
    if not url:
        return ""
    parsed = urlparse(url)
    return (parsed.hostname or "").lower()


def is_same_site(candidate_url: str, target_url: str, include_subdomains: bool) -> bool:
    """True if candidate_url belongs to the same site as target_url.

    With include_subdomains=True, hosts sharing the registered domain match
    (www.example.com, de.example.com, example.com all match each other).
    With include_subdomains=False, only exact host matches count.
    """
    if not candidate_url or not target_url:
        return False
    if include_subdomains:
        cand = registered_domain(candidate_url)
        targ = registered_domain(target_url)
        return bool(cand) and cand == targ
    return host(candidate_url) == host(target_url)


async def get_or_create_profile(db: AsyncSession, domain: str) -> Optional[SiteProfile]:
    """Look up the profile for a domain, creating it with defaults if missing."""
    if not domain:
        return None
    profile = await db.get(SiteProfile, domain)
    if profile is None:
        profile = SiteProfile(domain=domain, include_subdomains=True)
        db.add(profile)
        await db.flush()
    return profile
