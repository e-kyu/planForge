# -*- coding: utf-8 -*-
"""Plan 테이블 — plan 세대. markdown이 콘텐츠의 유일 원본 (원칙 1 — SSOT)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base
from app.shared.types import JSONVariant, UTCDateTime, StrEnum, UpdatedAtMixin, _enum


class PlanStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class PlanOrigin(StrEnum):
    INTERVIEW = "interview"
    EDIT = "edit"
    REVIEW = "review"


class Plan(UpdatedAtMixin, Base):
    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("project_id", "version_no", name="uq_project_planver"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)  # 1부터, project별 독립
    markdown: Mapped[str] = mapped_column(Text)  # 원칙 1 — SSOT
    docs: Mapped[list | None] = mapped_column(JSONVariant, nullable=True)  # 파싱 캐시
    parsed_ok: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PlanStatus] = mapped_column(
        _enum(PlanStatus), default=PlanStatus.DRAFT, server_default="draft"
    )
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    origin: Mapped[PlanOrigin] = mapped_column(
        _enum(PlanOrigin), default=PlanOrigin.INTERVIEW, server_default="interview"
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())