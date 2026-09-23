# -*- coding: utf-8 -*-
"""projects 모듈 퍼사드 — 타 모듈의 유일한 진입점 (가이드 §3 Facade)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.shared.errors import http_404

from .infrastructure.models import Project, ProjectStatus

__all__ = ["ProjectStatus", "get_project", "require_project", "project_slug"]


def get_project(db: Session, project_id: int) -> Project | None:
    return db.get(Project, project_id)


def require_project(db: Session, project_id: int) -> Project:
    p = get_project(db, project_id)
    if p is None:
        raise http_404(f"프로젝트 없음: {project_id}")
    return p


def project_slug(db: Session, project_id: int) -> str:
    return require_project(db, project_id).slug