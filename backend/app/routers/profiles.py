"""Site profile endpoints — per-domain settings used by domain matching."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.models import SiteProfile, TrackingJob
from ..models.schemas import SiteProfileResponse, SiteProfileUpdate
from ..services.domain_match import registered_domain

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.get("", response_model=list[SiteProfileResponse])
async def list_profiles(db: AsyncSession = Depends(get_db)):
    # Backfill: any tracked domain without a profile gets one with defaults so
    # the Settings page shows every site the user has jobs for.
    job_rows = await db.execute(select(TrackingJob.target_url, TrackingJob.target_domain))
    domains = set()
    for url, dom in job_rows.all():
        if url:
            domains.add(registered_domain(url))
        elif dom:
            d = dom.lower()
            domains.add(registered_domain(f"https://{d}/") or d)
    domains.discard("")

    existing_rows = await db.execute(select(SiteProfile.domain))
    existing = {d for (d,) in existing_rows.all()}

    created = False
    for d in domains - existing:
        db.add(SiteProfile(domain=d, include_subdomains=True))
        created = True
    if created:
        await db.commit()

    rows = await db.execute(select(SiteProfile).order_by(SiteProfile.domain))
    return [SiteProfileResponse.model_validate(p) for p in rows.scalars().all()]


@router.get("/{domain}", response_model=SiteProfileResponse)
async def get_profile(domain: str, db: AsyncSession = Depends(get_db)):
    profile = await db.get(SiteProfile, domain.lower())
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return SiteProfileResponse.model_validate(profile)


@router.put("/{domain}", response_model=SiteProfileResponse)
async def upsert_profile(
    domain: str,
    payload: SiteProfileUpdate,
    db: AsyncSession = Depends(get_db),
):
    domain = domain.lower()
    profile = await db.get(SiteProfile, domain)
    if profile is None:
        profile = SiteProfile(domain=domain, include_subdomains=payload.include_subdomains)
        db.add(profile)
    else:
        profile.include_subdomains = payload.include_subdomains
    await db.commit()
    await db.refresh(profile)
    return SiteProfileResponse.model_validate(profile)
