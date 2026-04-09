"""Tracking jobs CRUD endpoints."""
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models.models import TrackingJob, TrackingResult
from ..models.schemas import JobCreate, JobUpdate, JobResponse, ResultResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


async def _enrich_job(job: TrackingJob, db: AsyncSession) -> JobResponse:
    """Add latest result info to job response."""
    response = JobResponse.model_validate(job)

    # Get latest two results for this job
    stmt = (
        select(TrackingResult)
        .where(TrackingResult.job_id == job.id, TrackingResult.error.is_(None))
        .order_by(desc(TrackingResult.checked_at))
        .limit(2)
    )
    result = await db.execute(stmt)
    recent = list(result.scalars().all())

    if recent:
        latest = recent[0]
        response.latest_position = latest.organic_position
        response.latest_result_url = latest.result_url
        response.latest_aio_present = latest.aio_present
        response.latest_aio_url_cited = latest.aio_url_cited
        response.latest_aio_citation_url = latest.aio_citation_url
        response.last_checked = latest.checked_at

        if len(recent) > 1 and latest.organic_position and recent[1].organic_position:
            response.previous_position = recent[1].organic_position
            response.position_change = recent[1].organic_position - latest.organic_position

    return response


@router.get("", response_model=list[JobResponse])
async def list_jobs(db: AsyncSession = Depends(get_db)):
    stmt = select(TrackingJob).order_by(desc(TrackingJob.created_at))
    result = await db.execute(stmt)
    jobs = result.scalars().all()
    return [await _enrich_job(j, db) for j in jobs]


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(job_data: JobCreate, db: AsyncSession = Depends(get_db)):
    job = TrackingJob(**job_data.model_dump())
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return await _enrich_job(job, db)


@router.put("/{job_id}", response_model=JobResponse)
async def update_job(job_id: str, job_data: JobUpdate, db: AsyncSession = Depends(get_db)):
    job = await db.get(TrackingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    for key, value in job_data.model_dump(exclude_unset=True).items():
        setattr(job, key, value)
    await db.commit()
    await db.refresh(job)
    return await _enrich_job(job, db)


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(TrackingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await db.delete(job)
    await db.commit()


@router.post("/import", status_code=201)
async def import_jobs(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """Bulk import jobs from CSV. Expected columns: target_url, query, gl, hl"""
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    created = 0
    errors = []
    for i, row in enumerate(reader, start=2):
        try:
            target_url = row.get("target_url", "").strip()
            query = row.get("query", "").strip()
            if not target_url or not query:
                errors.append(f"Row {i}: missing target_url or query")
                continue
            job = TrackingJob(
                target_url=target_url,
                query=query,
                gl=row.get("gl", "us").strip() or "us",
                hl=row.get("hl", "en").strip() or "en",
            )
            db.add(job)
            created += 1
        except Exception as e:
            errors.append(f"Row {i}: {str(e)}")

    await db.commit()
    return {"created": created, "errors": errors}


@router.get("/{job_id}/results", response_model=list[ResultResponse])
async def get_job_results(
    job_id: str,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(TrackingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    stmt = (
        select(TrackingResult)
        .where(TrackingResult.job_id == job_id)
        .options(selectinload(TrackingResult.aio_citations), selectinload(TrackingResult.organic_results))
        .order_by(desc(TrackingResult.checked_at))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    results = result.scalars().all()

    return [ResultResponse.model_validate(r) for r in results]
