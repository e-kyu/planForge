# -*- coding: utf-8 -*-
"""ReviewReport 테이블 — 검수 리포트 (FR-4). plan 세대 1개당 검수 결과 1건 이상."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base
from app.shared.types import JSONVariant, UTCDateTime, UpdatedAtMixin


class ReviewReport(UpdatedAtMixin, Base):
    """findings는 numcheck.Finding + LLM 발견사항을 통합한 리스트
    [{code, severity, where, message, suggestion?}]. 심각도: red(사실 오류·수치
    불일치) / yellow(표현·구조) / white(선택). 수정은 plan 세대 교체(revise→approve)
    후 파생물 재생성으로만 한다 (FR-4.3 — 파생물 직접 수정 금지)."""

    __tablename__ = "review_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)  # 검수 대상 세대
    findings: Mapped[list] = mapped_column(JSONVariant, default=list)
    red_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    yellow_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    white_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    llm_ok: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())