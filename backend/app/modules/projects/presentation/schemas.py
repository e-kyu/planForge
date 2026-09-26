# -*- coding: utf-8 -*-
"""projects 프레젠테이션 스키마 — openapi-typescript로 TS 타입 생성 (§3.1 계약 잠금)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.shared.workspace import SLUG_RE


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