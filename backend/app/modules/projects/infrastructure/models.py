# -*- coding: utf-8 -*-
"""Project 테이블 — 추적성 사슬(§5)의 뿌리: Project → InterviewSession → Fact → …"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.db import Base
from app.shared.types import UTCDateTime, StrEnum, UpdatedAtMixin, _enum


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Project(UpdatedAtMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[ProjectStatus] = mapped_column(
        _enum(ProjectStatus), default=ProjectStatus.ACTIVE, server_default="active"
    )
    owner: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 추후 접근제어 확장(§5)
    workspace_path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    sessions: Mapped[list["InterviewSession"]] = relationship(back_populates="project")