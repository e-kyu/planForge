# -*- coding: utf-8 -*-
"""derivatives 모듈 퍼사드 — 타 모듈의 유일한 진입점 (가이드 §3 Facade)."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .infrastructure.models import Build, Derivative, DerivativeKind

__all__ = [
    "DerivativeKind", "has_any", "list_for_plan", "list_builds",
    "delete_project_data",
]


def has_any(db: Session, project_id: int) -> bool:
    """파생물이 하나라도 있는지 — 검수 전제(파생물 먼저 생성) 확인용."""
    return db.scalar(select(Derivative.id).where(Derivative.project_id == project_id).limit(1)) is not None


def list_for_plan(db: Session, project_id: int, plan_id: int) -> list[Derivative]:
    """같은 plan 세대의 파생물 (id 오름차순) — 검수 대조용."""
    return list(db.scalars(
        select(Derivative).where(Derivative.project_id == project_id,
                                 Derivative.plan_id == plan_id)
    ))


def list_builds(db: Session, project_id: int) -> list[Build]:
    return list(db.scalars(
        select(Build).where(Build.project_id == project_id).order_by(Build.id)
    ))


def delete_project_data(db: Session, project_id: int) -> None:
    db.execute(delete(Build).where(Build.project_id == project_id))
    db.execute(delete(Derivative).where(Derivative.project_id == project_id))