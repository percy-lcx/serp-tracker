from datetime import datetime
from pydantic import BaseModel


class JobCreate(BaseModel):
    target_url: str
    query: str
    gl: str = "us"
    hl: str = "en"
    is_active: bool = True


class JobUpdate(BaseModel):
    target_url: str | None = None
    query: str | None = None
    gl: str | None = None
    hl: str | None = None
    is_active: bool | None = None


class JobResponse(BaseModel):
    id: str
    target_url: str
    query: str
    gl: str
    hl: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    latest_position: int | None = None
    previous_position: int | None = None
    position_change: int | None = None
    latest_aio_present: bool | None = None
    latest_aio_url_cited: bool | None = None
    last_checked: datetime | None = None

    model_config = {"from_attributes": True}


class AioCitationResponse(BaseModel):
    id: str
    position: int
    cited_url: str
    cited_title: str | None
    is_target: bool

    model_config = {"from_attributes": True}


class ResultResponse(BaseModel):
    id: str
    job_id: str
    run_id: str
    checked_at: datetime
    organic_position: int | None
    organic_page: int | None
    result_url: str | None
    result_title: str | None
    result_description: str | None
    total_organic_results: int
    aio_present: bool
    aio_url_cited: bool
    aio_citation_position: int | None
    aio_content: str | None
    screenshot_page1_path: str | None
    screenshot_page2_path: str | None
    screenshot_aio_path: str | None
    error: str | None
    aio_citations: list[AioCitationResponse] = []

    model_config = {"from_attributes": True}


class ResultBrief(BaseModel):
    id: str
    job_id: str
    run_id: str
    checked_at: datetime
    organic_position: int | None
    organic_page: int | None
    aio_present: bool
    aio_url_cited: bool
    error: str | None

    model_config = {"from_attributes": True}


class RunCreate(BaseModel):
    job_ids: list[str] | None = None
    all_active: bool = False


class RunResponse(BaseModel):
    id: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    total_jobs: int
    completed_jobs: int
    failed_jobs: int

    model_config = {"from_attributes": True}


class RunDetailResponse(RunResponse):
    results: list[ResultBrief] = []


class StatsResponse(BaseModel):
    total_active_jobs: int
    total_jobs: int
    last_run_date: datetime | None
    last_run_status: str | None
    last_run_completed: int | None
    last_run_failed: int | None
    avg_position_change: float | None


class WebSocketMessage(BaseModel):
    type: str
    run_id: str | None = None
    job_id: str | None = None
    message: str | None = None
    progress: dict | None = None
