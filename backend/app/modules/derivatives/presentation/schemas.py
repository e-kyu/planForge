# -*- coding: utf-8 -*-
"""derivatives 프레젠테이션 스키마 — openapi-typescript로 TS 타입 생성 (§3.1 계약 잠금)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DerivativeCreate(BaseModel):
    kind: str  # slides | report
    doc: str | None = None
    fmts: list[str] | None = None  # report 빌드 포맷 (기본 3종)


class DerivativeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    kind: str
    doc: str
    slides_count: int
    sections_count: int
    unconfirmed: list | None
    attempts: int
    created_at: object


class BuildOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    derivative_id: int
    doc_kind: str
    ext: str
    version_no: int
    title: str
    file_path: str
    size_bytes: int
    created_at: object