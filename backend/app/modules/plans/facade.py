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
    "latest_generations_by_doc", "latest_generations_by_project_doc",
    "delete_project_plans",
]


def get_plan(db: Session, plan_id: int) -> Plan | None:
    return db.get(Plan, plan_id)


def require_plan(db: Session, plan_id: int) -> Plan:
    p = get_plan(db, plan_id)
    if p is None:
        raise http_404(f"plan 없음: {plan_id}")
    return p


def latest_approved(db: Session, project_id: int,
                    doc_slug: str | None = None) -> Plan | None:
    """최신 승인 세대 — 승인본은 항상 하나(승인 시 이전 세대 SUPERSEDED).

    doc_slug가 주어지면 그 문서의 최신 승인 세대로 좁힌다
    (None = 문서 무관, 기존 계약 — 기존 호출자 무수정).
    """
    q = select(Plan).where(
        Plan.project_id == project_id, Plan.status == PlanStatus.APPROVED)
    if doc_slug is not None:
        q = q.where(Plan.doc_slug == doc_slug)
    return db.scalar(q.order_by(Plan.version_no.desc()).limit(1))


def next_version_no(db: Session, project_id: int) -> int:
    max_ver = db.scalar(
        select(Plan.version_no).where(Plan.project_id == project_id)
        .order_by(Plan.version_no.desc()).limit(1)
    )
    return (max_ver or 0) + 1


def create_generation(db: Session, project_id: int, *, markdown: str,
                      docs=None, parsed_ok: bool = False, status=PlanStatus.DRAFT,
                      origin, doc_slug: str | None = None) -> Plan:
    """새 plan 세대 생성 — 무손실 채번(원칙 5 계열): version_no는 project별 단조 증가.

    doc_slug는 세대가 속한 문서(루프) 식별자(None = 레거시/문서 무관). 채번은
    문서별로 재시작하지 않는다 — uq_project_planver(프로젝트 전체 단조) 유지.
    커밋은 호출자 트랜잭션에서. 호출자: 인터뷰 write_plan·revise·plan_revise job.
    """
    p = Plan(project_id=project_id, version_no=next_version_no(db, project_id),
             markdown=markdown, docs=docs, parsed_ok=parsed_ok, status=status,
             origin=origin, doc_slug=doc_slug)
    db.add(p)
    db.flush()
    return p


def latest_generations_by_doc(db: Session, project_id: int) -> dict[str | None, Plan]:
    """문서별(없음 None 포함) 최신 plan 세대 — docloops 상태 API의 plan_version 파생값.

    상태 무관 최신(version_no desc) — 키별 최첨 행만 남긴다. plan 진행상황의 SSOT은
    plans 행이므로(docloops 원칙) 루프 행에 캐시하지 않고 역참조로 산출한다.
    """
    out: dict[str | None, Plan] = {}
    rows = db.scalars(
        select(Plan).where(Plan.project_id == project_id)
        .order_by(Plan.version_no.desc())
    )
    for r in rows:
        if r.doc_slug not in out:
            out[r.doc_slug] = r
    return out


def latest_generations_by_project_doc(
        db: Session, project_ids: list[int]) -> dict[tuple[int, str | None], Plan]:
    """프로젝트 배치·문서별(없음 None 포함) 최신 plan 세대 — (project_id, doc_slug) 키.

    목록 화면의 N+1 방지용 — 쿼리 1회를 version_no desc로 훑어 키별 최신만
    파이썬에서 채택한다 (latest_generations_by_doc의 다중 프로젝트판).
    """
    out: dict[tuple[int, str | None], Plan] = {}
    rows = db.scalars(
        select(Plan).where(Plan.project_id.in_(project_ids))
        .order_by(Plan.version_no.desc())
    )
    for r in rows:
        key = (r.project_id, r.doc_slug)
        if key not in out:
            out[key] = r
    return out


def delete_project_plans(db: Session, project_id: int) -> None:
    db.execute(delete(Plan).where(Plan.project_id == project_id))