from datetime import datetime
from typing import Optional, List, Dict

from pydantic import BaseModel, Field, computed_field


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
    is_active: Optional[bool] = Field(default=None, validation_alias="active")


class JobResponse(BaseModel):
    id: str
    target_url: str
    query: str
    gl: str
    hl: str
    is_active: bool = Field(serialization_alias="active")
    created_at: datetime
    updated_at: datetime
    latest_position: Optional[int] = Field(default=None, serialization_alias="position")
    previous_position: Optional[int] = None
    position_change: Optional[int] = None
    latest_result_url: Optional[str] = None
    latest_aio_present: Optional[bool] = None
    latest_aio_url_cited: Optional[bool] = Field(default=None, serialization_alias="aio_cited")
    latest_aio_citation_url: Optional[str] = None
    last_checked: Optional[datetime] = None

    @computed_field
    @property
    def aio_status(self) -> Optional[str]:
        if self.latest_aio_present is None:
            return None
        if not self.latest_aio_present:
            return "absent"
        if self.latest_aio_url_cited:
            return "cited"
        return "present"

    model_config = {"from_attributes": True, "populate_by_name": True}


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
    organic_position: Optional[int] = Field(default=None, serialization_alias="position")
    organic_page: Optional[int] = None
    result_url: Optional[str] = None
    result_title: Optional[str] = None
    result_description: Optional[str] = None
    total_organic_results: int = 0
    aio_present: bool = False
    aio_url_cited: bool = Field(default=False, serialization_alias="aio_cited")
    aio_citation_position: Optional[int] = Field(default=None, serialization_alias="aio_position")
    aio_citation_url: Optional[str] = None
    aio_content: Optional[str] = None
    screenshot_page1_path: Optional[str] = None
    screenshot_page2_path: Optional[str] = None
    screenshot_aio_path: Optional[str] = None
    error: Optional[str] = None
    debug_log: Optional[str] = None
    aio_citations: List[AioCitationResponse] = []

    model_config = {"from_attributes": True, "populate_by_name": True}


class ResultBrief(BaseModel):
    id: str
    job_id: str
    run_id: str
    checked_at: datetime
    organic_position: Optional[int] = Field(default=None, serialization_alias="position")
    organic_page: Optional[int] = None
    result_url: Optional[str] = None
    aio_present: bool = False
    aio_url_cited: bool = Field(default=False, serialization_alias="aio_cited")
    aio_citation_url: Optional[str] = None
    error: Optional[str] = None

    model_config = {"from_attributes": True, "populate_by_name": True}


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
