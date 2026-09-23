# -*- coding: utf-8 -*-
"""Job 테이블 — DB 작업 큐. 단일 워커가 직렬 실행한다 (원칙 5 — 빌더 스레드 비안전)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base
from app.shared.types import JSONVariant, UTCDateTime, StrEnum, UpdatedAtMixin, _enum


class JobType(StrEnum):
    DERIVE_BUILD = "derive_build"
    REVIEW = "review"
    PLAN_REVISE = "plan_revise"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobErrorClass(StrEnum):
    VALIDATION = "validation"
    SCHEMA = "schema"
    LLM = "llm"
    BUILDER = "builder"
    INTERNAL = "internal"


class Job(UpdatedAtMixin, Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    type: Mapped[JobType] = mapped_column(_enum(JobType))
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus), default=JobStatus.QUEUED, server_default="queued"
    )
    payload: Mapped[dict] = mapped_column(JSONVariant)
    result: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    error_class: Mapped[JobErrorClass | None] = mapped_column(_enum(JobErrorClass), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())