# -*- coding: utf-8 -*-
"""facts 모듈 퍼사드 — 타 모듈의 유일한 진입점 (가이드 §3 Facade)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .infrastructure.models import Fact, FactOrigin, FactStatus

__all__ = [
    "FactStatus", "FactOrigin",
    "append_facts", "list_active_facts", "delete_project_facts",
]


def append_facts(db: Session, project_id: int, session_id: int | None,
                 items: list[dict]) -> list[Fact]:
    """확정 팩트 적립 (원칙 4) — 인터뷰 게이트를 통과한 항목만.

    items: [{content, source?}] — 호출자(인터뷰 게이트)가 승인·수정을 마친 팩트.
    커밋은 호출자 트랜잭션에서.
    """
    out: list[Fact] = []
    for it in items:
        f = Fact(project_id=project_id, session_id=session_id, date=date.today(),
                 content=it["content"], source=it.get("source", ""),
                 origin=FactOrigin.INTERVIEW)
        db.add(f)
        out.append(f)
    db.flush()
    return out


def list_active_facts(db: Session, project_id: int) -> list[Fact]:
    """활성 팩트 (id 오름차순) — 인터뷰 주입·검수 대조가 쓴다 (FR-4.4 전제)."""
    return list(db.scalars(
        select(Fact).where(Fact.project_id == project_id, Fact.status == FactStatus.ACTIVE)
        .order_by(Fact.id)
    ))


def delete_project_facts(db: Session, project_id: int) -> None:
    db.execute(delete(Fact).where(Fact.project_id == project_id))