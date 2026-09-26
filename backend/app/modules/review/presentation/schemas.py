# -*- coding: utf-8 -*-
"""review 프레젠테이션 스키마 — openapi-typescript로 TS 타입 생성 (§3.1 계약 잠금)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FindingOut(BaseModel):
    code: str
    severity: str
    where: str
    message: str
    suggestion: str | None = None  # LLM 발견사항의 plan 수정 방향 (결정론 발견사항엔 없음)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    plan_id: int
    findings: list[FindingOut]
    red_count: int
    yellow_count: int
    white_count: int
    llm_ok: bool
    summary: str
    created_at: object