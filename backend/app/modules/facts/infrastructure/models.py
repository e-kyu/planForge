# -*- coding: utf-8 -*-
"""Fact 테이블 — 팩트 선(先)적립의 저장소 (원칙 4). archived는 압축(FR-6.1) 이력."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base
from app.shared.types import UTCDateTime, StrEnum, _enum


class FactStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class FactOrigin(StrEnum):
    INTERVIEW = "interview"
    REVIEW = "review"
    MANUAL = "manual"


class Fact(Base):
    __tablename__ = "facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("interview_sessions.id"), nullable=True
    )
    date: Mapped[date] = mapped_column(Date, default=date.today)
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(300), default="", server_default="")
    status: Mapped[FactStatus] = mapped_column(
        _enum(FactStatus), default=FactStatus.ACTIVE, server_default="active"
    )
    origin: Mapped[FactOrigin] = mapped_column(
        _enum(FactOrigin), default=FactOrigin.INTERVIEW, server_default="interview"
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())