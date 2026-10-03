# -*- coding: utf-8 -*-
"""sources 프레젠테이션 스키마 — openapi-typescript로 TS 타입 생성 (§3.1 계약 잠금)."""
from __future__ import annotations

from pydantic import BaseModel


class SourceOut(BaseModel):
    name: str
    size: int
    dir: str  # project | global (글로벌은 읽기 전용)
    mtime: float


class OverviewOut(BaseModel):
    """소스 탭 웹 작성 개요 문서 (sources/overview.md — 파일이 곧 SSOT)."""
    exists: bool
    content: str  # 파일이 없으면 "" (빈 뼈대는 프론트에서 주입)
    size: int
    mtime: float | None  # 파일이 없으면 None


class OverviewSave(BaseModel):
    content: str