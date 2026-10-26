# -*- coding: utf-8 -*-
"""DocLoop 테이블 — 문서별 선순환 루프 상태 (proposal · uiux-design · dev-design).

3종 문서는 각각 독립 진행한다 (independent-doc-loops): 생성 시 전부 active로 시드되고,
plan 승인 훅은 자기 문서 행만 done으로 전환한다. plan 진행상황은 plans 행 역참조가
SSOT이므로 루프에 plan_id·plan_version 등 파생 상태를 캐시하지 않는다 (이중 원본
방지). doc_slug NULL = 레거시 (문서 루프 도입 전).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base
from app.shared.types import UTCDateTime, StrEnum, UpdatedAtMixin, _enum


class DocLoopStatus(StrEnum):
    LOCKED = "locked"      # 도달 불가 잔여 상태 (안전망 409 분기만) — 신규 시드는 전부 active
    ACTIVE = "active"      # 버튼 활성 — 세션 생성 가능
    DONE = "done"          # 자기 plan 승인 완료 — 재작업(세션 재생성) 가능


class DocLoop(UpdatedAtMixin, Base):
    __tablename__ = "doc_loops"
    __table_args__ = (UniqueConstraint("project_id", "doc_slug", name="uq_project_docloop"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    doc_slug: Mapped[str] = mapped_column(String(32))
    status: Mapped[DocLoopStatus] = mapped_column(
        _enum(DocLoopStatus), default=DocLoopStatus.ACTIVE, server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())