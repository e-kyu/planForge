# -*- coding: utf-8 -*-
"""sources 프레젠테이션 스키마 — openapi-typescript로 TS 타입 생성 (§3.1 계약 잠금)."""
from __future__ import annotations

from pydantic import BaseModel


class SourceOut(BaseModel):
    name: str
    size: int
    dir: str  # project | global (글로벌은 읽기 전용)
    mtime: float