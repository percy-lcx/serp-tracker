"""Dashboard stats endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.models import TrackingJob, TrackingRun
from ..models.schemas import StatsResponse

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    # Total jobs
    total_result = await db.execute(select(func.count(TrackingJob.id)))
    total_jobs = total_result.scalar() or 0

    active_result = await db.execute(
        select(func.count(TrackingJob.id)).where(TrackingJob.is_active == True)
    )
    total_active = active_result.scalar() or 0

    # Last run
    last_run_result = await db.execute(
        select(TrackingRun).order_by(desc(TrackingRun.started_at)).limit(1)
    )
    last_run = last_run_result.scalar_one_or_none()

    return StatsResponse(
        total_active_jobs=total_active,
        total_jobs=total_jobs,
        last_run_date=last_run.started_at if last_run else None,
        last_run_status=last_run.status if last_run else None,
        last_run_completed=last_run.completed_jobs if last_run else None,
        last_run_failed=last_run.failed_jobs if last_run else None,
        avg_position_change=None,
    )
