# -*- coding: utf-8 -*-
"""jobs 프레젠테이션 스키마 — openapi-typescript로 TS 타입 생성 (§3.1 계약 잠금).

JobOut은 plans·derivatives·review의 202 응답이 공유하는 큐 진입 계약이다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    status: str
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error_class: str | None
    error: str | None
    attempts: int
    created_at: datetime