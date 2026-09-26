# -*- coding: utf-8 -*-
"""plans 프레젠테이션 스키마 — openapi-typescript로 TS 타입 생성 (§3.1 계약 잠금)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    version_no: int
    markdown: str
    docs: list | None
    parsed_ok: bool
    status: str
    origin: str
    approved_at: object | None
    created_at: object


class PlanRevise(BaseModel):
    markdown: str


class PlanReviseFromReview(BaseModel):
    review_id: int
    finding_indices: list[int] | None = None  # None → 전체 발견사항