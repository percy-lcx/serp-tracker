"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import SCREENSHOT_DIR
from .database import init_db
from .routers import jobs, profiles, results, runs, stats
from .services.cleanup import cleanup_old_screenshots

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    await cleanup_old_screenshots()
    logger.info("SERP Tracker started")
    yield
    # Shutdown
    logger.info("SERP Tracker shutting down")


app = FastAPI(
    title="SERP Ranking Tracker",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(runs.router)
app.include_router(results.router)
app.include_router(stats.router)
app.include_router(profiles.router)

# Serve frontend static files in production
frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
