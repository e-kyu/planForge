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


class SkipOut(BaseModel):
    """스킵된 zip 멤버 보고 — 원명(정규화 전)으로 사용자가 원본 zip과 대조할 수 있게 한다."""
    name: str
    reason: str


class UploadResult(BaseModel):
    """소스 업로드 응답 — 기존 단일 SourceOut의 래핑 확장.

    zip 업로드는 멤버마다 저장/스킵이 갈리므로 saved·skipped를 함께 보고한다. 단일
    파일은 saved 1건·skipped 빈 배열이다 (거부는 409 — 스킵이 아니라 거부다).
    """
    saved: list[SourceOut]
    skipped: list[SkipOut]