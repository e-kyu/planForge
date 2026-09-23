# -*- coding: utf-8 -*-
"""Derivative·Build 테이블 — plan 세대에 바인딩된 파생물과 결정론 빌드 채번.

- 원칙 5(무손실 채번): builds는 빌더 fs glob의 미러(채번 권위는 파일시스템), 절대 재사용 없음
- 원칙 1(SSOT): work/*.json은 미러 — 파생물 재생성은 항상 plan에서
- 추적성(§5): builds → derivative_id → plan_id 역참조 사슬
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base
from app.shared.types import JSONVariant, UTCDateTime, StrEnum, UpdatedAtMixin, _enum


class DerivativeKind(StrEnum):
    SLIDES = "slides"
    REPORT = "report"


class Derivative(UpdatedAtMixin, Base):
    __tablename__ = "derivatives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)  # 세대 바인딩
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[DerivativeKind] = mapped_column(_enum(DerivativeKind))
    doc: Mapped[str] = mapped_column(String(100))
    json: Mapped[dict] = mapped_column(JSONVariant)  # work/*.json 미러 (재생성 원본은 plan)
    slides_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sections_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    unconfirmed: Mapped[list | None] = mapped_column(JSONVariant, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())


class Build(UpdatedAtMixin, Base):
    __tablename__ = "builds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)
    derivative_id: Mapped[int] = mapped_column(ForeignKey("derivatives.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    doc_kind: Mapped[str] = mapped_column(String(100))
    ext: Mapped[str] = mapped_column(String(8))
    version_no: Mapped[int] = mapped_column(Integer)  # 빌더 fs glob의 미러
    title: Mapped[str] = mapped_column(String(300))
    file_path: Mapped[str] = mapped_column(String(500))  # 워크스페이스 상대 경로
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())