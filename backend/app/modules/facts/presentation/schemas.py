# -*- coding: utf-8 -*-
"""facts 프레젠테이션 스키마 — openapi-typescript로 TS 타입 생성 (§3.1 계약 잠금)."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class FactCreate(BaseModel):
    content: str
    source: str = ""
    date: dt.date | None = None
    origin: str = "manual"


class FactUpdate(BaseModel):
    content: str | None = None
    source: str | None = None
    status: str | None = None  # active | archived (FR-6.1 압축 대비)


class FactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    session_id: int | None
    date: dt.date
    content: str
    source: str
    status: str
    origin: str
    created_at: object


class CompactGroup(BaseModel):
    topic: str = ""
    keep_id: int
    archive_ids: list[int] = []
    reason: str = ""


class CompactPreview(BaseModel):
    ok: bool
    summary: str = ""
    warning: str | None = None
    groups: list[CompactGroup]
    facts: list[FactOut]  # 활성 팩트 전체 (프론트 표시용)


class CompactApplyRequest(BaseModel):
    groups: list[CompactGroup]


class CompactApplyResult(BaseModel):
    archived: list[int]
    active_remaining: int
    log_path: str
    archive_path: str
    warnings: list[str]