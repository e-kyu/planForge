# -*- coding: utf-8 -*-
"""review 모듈 퍼사드 — 타 모듈의 유일한 진입점 (가이드 §3 Facade)."""
from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .infrastructure.models import ReviewReport

__all__ = ["get_report", "delete_project_data"]


def get_report(db: Session, review_id: int) -> ReviewReport | None:
    return db.get(ReviewReport, review_id)


def delete_project_data(db: Session, project_id: int) -> None:
    db.execute(delete(ReviewReport).where(ReviewReport.project_id == project_id))