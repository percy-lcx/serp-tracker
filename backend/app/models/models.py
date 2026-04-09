from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def utcnow():
    return datetime.now(timezone.utc)


def new_uuid():
    return str(uuid.uuid4())


class TrackingJob(Base):
    __tablename__ = "tracking_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    gl: Mapped[str] = mapped_column(String(10), nullable=False, default="us")
    hl: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    results: Mapped[List[TrackingResult]] = relationship(back_populates="job", cascade="all, delete-orphan")


class TrackingRun(Base):
    __tablename__ = "tracking_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    total_jobs: Mapped[int] = mapped_column(Integer, default=0)
    completed_jobs: Mapped[int] = mapped_column(Integer, default=0)
    failed_jobs: Mapped[int] = mapped_column(Integer, default=0)

    results: Mapped[List[TrackingResult]] = relationship(back_populates="run", cascade="all, delete-orphan")


class TrackingResult(Base):
    __tablename__ = "tracking_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("tracking_jobs.id", ondelete="CASCADE"))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("tracking_runs.id", ondelete="CASCADE"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    organic_position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    organic_page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    result_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_organic_results: Mapped[int] = mapped_column(Integer, default=0)
    aio_present: Mapped[bool] = mapped_column(Boolean, default=False)
    aio_url_cited: Mapped[bool] = mapped_column(Boolean, default=False)
    aio_citation_position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    aio_citation_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    aio_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    screenshot_page1_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    screenshot_page2_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    screenshot_aio_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    debug_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    job: Mapped[TrackingJob] = relationship(back_populates="results")
    run: Mapped[TrackingRun] = relationship(back_populates="results")
    aio_citations: Mapped[List[AioCitation]] = relationship(back_populates="result", cascade="all, delete-orphan")


class AioCitation(Base):
    __tablename__ = "aio_citations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    result_id: Mapped[str] = mapped_column(String(36), ForeignKey("tracking_results.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    cited_url: Mapped[str] = mapped_column(Text, nullable=False)
    cited_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_target: Mapped[bool] = mapped_column(Boolean, default=False)

    result: Mapped[TrackingResult] = relationship(back_populates="aio_citations")
