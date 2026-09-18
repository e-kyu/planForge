# -*- coding: utf-8 -*-
"""Pydantic v2 요청/응답 모델 — M3에서 openapi-typescript로 TS 타입 생성 (§3.1 계약 잠금)."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


# ---------------------------------------------------------------- projects (FR-1)

class ProjectCreate(BaseModel):
    slug: str
    title: str
    owner: str | None = None

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        if not SLUG_RE.fullmatch(v):
            raise ValueError("slug는 ASCII 소문자/숫자/하이픈(첫 글자는 영숫자)만 허용")
        if len(v) > 64:
            raise ValueError("slug는 64자 이하여야 합니다")
        return v


class ProjectUpdate(BaseModel):
    title: str | None = None
    status: Literal["active", "archived"] | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    status: str
    owner: str | None
    created_at: datetime


class JobRef(BaseModel):
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