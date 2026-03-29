"""Tracking runs endpoints."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models.models import TrackingJob, TrackingRun, TrackingResult
from ..models.schemas import RunCreate, RunResponse, RunDetailResponse, ResultBrief
from ..services.crawl_engine import RunManager, execute_run

router = APIRouter(tags=["runs"])


@router.post("/api/runs", response_model=RunResponse, status_code=201)
async def trigger_run(run_data: RunCreate, db: AsyncSession = Depends(get_db)):
    manager = RunManager.get_instance()
    if manager.active_run_id:
        raise HTTPException(status_code=409, detail="A run is already in progress")

    # Determine which jobs to run
    if run_data.all_active:
        stmt = select(TrackingJob).where(TrackingJob.is_active == True)
        result = await db.execute(stmt)
        jobs = list(result.scalars().all())
    elif run_data.job_ids:
        stmt = select(TrackingJob).where(TrackingJob.id.in_(run_data.job_ids))
        result = await db.execute(stmt)
        jobs = list(result.scalars().all())
    else:
        raise HTTPException(status_code=400, detail="Provide job_ids or set all_active=true")

    if not jobs:
        raise HTTPException(status_code=400, detail="No jobs found to run")

    # Create run record
    run = TrackingRun(total_jobs=len(jobs))
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Launch crawl in background
    job_ids = [j.id for j in jobs]
    asyncio.create_task(execute_run(run.id, job_ids))

    return RunResponse.model_validate(run)


@router.get("/api/runs", response_model=list[RunResponse])
async def list_runs(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(TrackingRun)
        .order_by(desc(TrackingRun.started_at))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return [RunResponse.model_validate(r) for r in result.scalars().all()]


@router.get("/api/runs/{run_id}", response_model=RunDetailResponse)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(TrackingRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    stmt = (
        select(TrackingResult)
        .where(TrackingResult.run_id == run_id)
        .order_by(TrackingResult.checked_at)
    )
    result = await db.execute(stmt)
    results = [ResultBrief.model_validate(r) for r in result.scalars().all()]

    response = RunDetailResponse.model_validate(run)
    response.results = results
    return response


@router.post("/api/runs/{run_id}/abort", status_code=200)
async def abort_run(run_id: str, db: AsyncSession = Depends(get_db)):
    manager = RunManager.get_instance()
    if manager.active_run_id != run_id:
        raise HTTPException(status_code=400, detail="This run is not currently active")
    manager.request_abort()
    return {"message": "Abort requested"}


@router.websocket("/ws/runs/{run_id}")
async def run_websocket(websocket: WebSocket, run_id: str):
    await websocket.accept()
    manager = RunManager.get_instance()
    manager.register_ws(run_id, websocket)
    try:
        while True:
            # Keep connection alive, receive any client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.unregister_ws(run_id, websocket)
