# -*- coding: utf-8 -*-
"""모델 공통 타입 프리미티브 — SQLite 단일 방언 (모든 모듈 models가 공유)."""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator

# SQLite 단일 방언 (2026-09-19 전환) — 방언 분기(with_variant) 없이 JSON 하나로 통일.
JSONVariant = JSON


class UTCDateTime(TypeDecorator):
    """DateTime(timezone=True) 시맨틱을 SQLite에 맞춘다.

    저장: aware → UTC 변환 후 naive 기록 (SQLite는 tz 보존 불가)
    로드: naive → UTC aware 부여 — 기존 timestamptz 계약(aware 반환) 유지,
    Pydantic이 +00:00 오프셋을 실어 직렬화한다.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class StrEnum(str, enum.Enum):
    """native_enum=False String Enum 공통 베이스 (SQLite에는 네이티브 ENUM 타입이 없다)."""

    def __str__(self) -> str:  # pragma: no cover - 표기 편의
        return self.value


def _enum(enum_cls, **kw):
    # value 기준 저장 (기본은 name 저장 — 'queued'가 'QUEUED'로 기록되는 문제 방지)
    return Enum(enum_cls, values_callable=lambda e: [m.value for m in e],
                native_enum=False, length=32, **kw)


class UpdatedAtMixin:
    """§5.3 공통 컬럼 — 갱신 시각. NULL은 아직 갱신되지 않은 행
    (append-only 행 — interview_messages·builds 등 — 은 대부분 NULL)."""

    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, onupdate=func.now())