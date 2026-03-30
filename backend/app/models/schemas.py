from datetime import datetime
from typing import Optional, List, Dict

from pydantic import BaseModel


class JobCreate(BaseModel):
    target_url: str
    query: str
    gl: str = "us"
    hl: str = "en"
    is_active: bool = True


class JobUpdate(BaseModel):
    target_url: Optional[str] = None
    query: Optional[str] = None
    gl: Optional[str] = None
    hl: Optional[str] = None
    is_active: Optional[bool] = None


class JobResponse(BaseModel):
    id: str
    target_url: str
    query: str
    gl: str
    hl: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    latest_position: Optional[int] = None
    previous_position: Optional[int] = None
    position_change: Optional[int] = None
    latest_aio_present: Optional[bool] = None
    latest_aio_url_cited: Optional[bool] = None
    last_checked: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AioCitationResponse(BaseModel):
    id: str
    position: int
    cited_url: str
    cited_title: Optional[str]
    is_target: bool

    model_config = {"from_attributes": True}


class ResultResponse(BaseModel):
    id: str
    job_id: str
    run_id: str
    checked_at: datetime
    organic_position: Optional[int]
    organic_page: Optional[int]
    result_url: Optional[str]
    result_title: Optional[str]
    result_description: Optional[str]
    total_organic_results: int
    aio_present: bool
    aio_url_cited: bool
    aio_citation_position: Optional[int]
    aio_content: Optional[str]
    screenshot_page1_path: Optional[str]
    screenshot_page2_path: Optional[str]
    screenshot_aio_path: Optional[str]
    error: Optional[str]
    aio_citations: List[AioCitationResponse] = []

    model_config = {"from_attributes": True}


class ResultBrief(BaseModel):
    id: str
    job_id: str
    run_id: str
    checked_at: datetime
    organic_position: Optional[int]
    organic_page: Optional[int]
    aio_present: bool
    aio_url_cited: bool
    error: Optional[str]

    model_config = {"from_attributes": True}


class RunCreate(BaseModel):
    job_ids: Optional[List[str]] = None
    all_active: bool = False


class RunResponse(BaseModel):
    id: str
    started_at: datetime
    completed_at: Optional[datetime]
    status: str
    total_jobs: int
    completed_jobs: int
    failed_jobs: int

    model_config = {"from_attributes": True}


class RunDetailResponse(RunResponse):
    results: List[ResultBrief] = []


class StatsResponse(BaseModel):
    total_active_jobs: int
    total_jobs: int
    last_run_date: Optional[datetime]
    last_run_status: Optional[str]
    last_run_completed: Optional[int]
    last_run_failed: Optional[int]
    avg_position_change: Optional[float]


class WebSocketMessage(BaseModel):
    type: str
    run_id: Optional[str] = None
    job_id: Optional[str] = None
    message: Optional[str] = None
    progress: Optional[Dict] = None
