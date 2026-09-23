# -*- coding: utf-8 -*-
"""plans 모듈 퍼사드 — 타 모듈의 유일한 진입점 (가이드 §3 Facade)."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.shared.errors import http_404

from .infrastructure.models import Plan, PlanOrigin, PlanStatus

__all__ = [
    "PlanStatus", "PlanOrigin",
    "get_plan", "require_plan", "latest_approved", "create_generation",
    "delete_project_plans",
]


def get_plan(db: Session, plan_id: int) -> Plan | None:
    return db.get(Plan, plan_id)


def require_plan(db: Session, plan_id: int) -> Plan:
    p = get_plan(db, plan_id)
    if p is None:
        raise http_404(f"plan 없음: {plan_id}")
    return p


def latest_approved(db: Session, project_id: int) -> Plan | None:
    """최신 승인 세대 — 승인본은 항상 하나(승인 시 이전 세대 SUPERSEDED)."""
    return db.scalar(
        select(Plan)
        .where(Plan.project_id == project_id, Plan.status == PlanStatus.APPROVED)
        .order_by(Plan.version_no.desc()).limit(1)
    )


def next_version_no(db: Session, project_id: int) -> int:
    max_ver = db.scalar(
        select(Plan.version_no).where(Plan.project_id == project_id)
        .order_by(Plan.version_no.desc()).limit(1)
    )
    return (max_ver or 0) + 1


def create_generation(db: Session, project_id: int, *, markdown: str,
                      docs=None, parsed_ok: bool = False, status=PlanStatus.DRAFT,
                      origin) -> Plan:
    """새 plan 세대 생성 — 무손실 채번(원칙 5 계열): version_no는 project별 단조 증가.

    커밋은 호출자 트랜잭션에서. 호출자: 인터뷰 write_plan·revise·plan_revise job.
    """
    p = Plan(project_id=project_id, version_no=next_version_no(db, project_id),
             markdown=markdown, docs=docs, parsed_ok=parsed_ok, status=status, origin=origin)
    db.add(p)
    db.flush()
    return p


def delete_project_plans(db: Session, project_id: int) -> None:
    db.execute(delete(Plan).where(Plan.project_id == project_id))