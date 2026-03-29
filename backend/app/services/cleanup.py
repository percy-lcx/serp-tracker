"""Screenshot retention cleanup."""
import logging
import shutil
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from ..config import SCREENSHOT_DIR, SCREENSHOT_RETENTION_DAYS
from ..database import async_session
from ..models.models import TrackingResult

logger = logging.getLogger(__name__)


async def cleanup_old_screenshots():
    """Delete screenshot directories older than retention period and nullify DB paths."""
    if not SCREENSHOT_DIR.exists():
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=SCREENSHOT_RETENTION_DAYS)
    deleted_count = 0

    for run_dir in SCREENSHOT_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        try:
            mtime = datetime.fromtimestamp(run_dir.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                shutil.rmtree(run_dir)
                deleted_count += 1
                run_id = run_dir.name

                async with async_session() as db:
                    await db.execute(
                        update(TrackingResult)
                        .where(TrackingResult.run_id == run_id)
                        .values(
                            screenshot_page1_path=None,
                            screenshot_page2_path=None,
                            screenshot_aio_path=None,
                        )
                    )
                    await db.commit()
        except Exception as e:
            logger.error("Error cleaning up %s: %s", run_dir, e)

    if deleted_count:
        logger.info("Cleaned up %d old screenshot directories", deleted_count)
