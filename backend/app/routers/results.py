"""Results and screenshots endpoints."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models.models import TrackingResult
from ..models.schemas import ResultResponse

router = APIRouter(prefix="/api/results", tags=["results"])


@router.get("/{result_id}", response_model=ResultResponse)
async def get_result(result_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    stmt = (
        select(TrackingResult)
        .where(TrackingResult.id == result_id)
        .options(selectinload(TrackingResult.aio_citations), selectinload(TrackingResult.organic_results))
    )
    result = await db.execute(stmt)
    tracking_result = result.scalar_one_or_none()
    if not tracking_result:
        raise HTTPException(status_code=404, detail="Result not found")
    return ResultResponse.model_validate(tracking_result)


@router.get("/{result_id}/screenshots/{screenshot_type}")
async def get_screenshot(result_id: str, screenshot_type: str, db: AsyncSession = Depends(get_db)):
    if screenshot_type not in ("page1", "page2", "aio"):
        raise HTTPException(status_code=400, detail="Invalid screenshot type")

    tracking_result = await db.get(TrackingResult, result_id)
    if not tracking_result:
        raise HTTPException(status_code=404, detail="Result not found")

    path_map = {
        "page1": tracking_result.screenshot_page1_path,
        "page2": tracking_result.screenshot_page2_path,
        "aio": tracking_result.screenshot_aio_path,
    }

    file_path = path_map[screenshot_type]
    if not file_path:
        raise HTTPException(status_code=404, detail="Screenshot not available")

    path = Path(file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Screenshot file not found on disk")

    return FileResponse(path, media_type="image/png")
