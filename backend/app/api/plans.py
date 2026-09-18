# -*- coding: utf-8 -*-
"""plan.md API (FR-2.8/2.9) — plan 세대 조회·승인·수정 게이트.

원칙 1(SSOT): 콘텐츠 원본은 DB plans.markdown. workspaces/*/plan.md는
미러이며 파생물 생성은 항상 이 원본에서 재생성된다.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from reportagent.plan import PlanError, filter_slides, parse_plan_text, validate_skeleton
from reportagent.plan import Plan as ParsedPlan

from ..db import get_db
from ..errors import http_404, http_409
from ..models import (
    InterviewSession,
    Plan,
    PlanOrigin,
    PlanStatus,
    Project,
    SessionPhase,
    SessionStatus,
)
from ..workspace import write_plan_mirror

router = APIRouter(tags=["plans"])


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    version_no: int
    markdown: str
    docs: list | None
    parsed_ok: bool
    status: str
    origin: str
    approved_at: object | None
    created_at: object


class PlanRevise(BaseModel):
    markdown: str


def _plan_or_404(db: Session, plan_id: int) -> "Plan":
    p = db.get(Plan, plan_id)
    if p is None:
        raise http_404(f"plan 없음: {plan_id}")
    return p


def _validate_markdown(markdown: str) -> ParsedPlan:
    """plan 포맷 + 골격 검증 (원칙 8 — 미달 시 PlanError → 422)."""
    plan = parse_plan_text(markdown)
    if len(plan.key_messages) != 3:
        raise PlanError(f"핵심 메시지는 정확히 3개여야 합니다 (현재 {len(plan.key_messages)}개)")
    for doc in plan.docs:
        validate_skeleton(filter_slides(plan.slides, doc))
    return plan


@router.get("/api/projects/{project_id}/plans", response_model=list[PlanOut])
def list_plans(project_id: int, db: Session = Depends(get_db)):
    if db.get(Project, project_id) is None:
        raise http_404(f"프로젝트 없음: {project_id}")
    plans = db.scalars(
        select(Plan).where(Plan.project_id == project_id).order_by(Plan.version_no)
    )
    return [PlanOut.model_validate(p) for p in plans]


@router.get("/api/plans/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    return PlanOut.model_validate(_plan_or_404(db, plan_id))


@router.post("/api/plans/{plan_id}/approve", response_model=PlanOut)
def approve_plan(plan_id: int, db: Session = Depends(get_db)):
    """승인 게이트 (FR-2.9) — 승인 전에 파생 단계로 넘어가지 않는다."""
    plan = _plan_or_404(db, plan_id)
    if plan.status != PlanStatus.DRAFT:
        raise http_409(f"DRAFT plan만 승인할 수 있습니다 (현재 {plan.status.value})")

    # 이전 승인본은 세대 교체 — 유효한 SSOT 승인본은 최신 하나
    for old in db.scalars(
        select(Plan)
        .where(Plan.project_id == plan.project_id, Plan.status == PlanStatus.APPROVED)
    ).all():
        old.status = PlanStatus.SUPERSEDED
    plan.status = PlanStatus.APPROVED
    plan.approved_at = datetime.now(timezone.utc)

    # plan을 작성한 세션 완료 처리
    for sess in db.scalars(
        select(InterviewSession)
        .where(InterviewSession.project_id == plan.project_id,
               InterviewSession.phase == SessionPhase.PLAN_REVIEW)
    ).all():
        sess.phase = SessionPhase.APPROVED
        sess.status = SessionStatus.DONE

    project = db.get(Project, plan.project_id)
    write_plan_mirror(Path(project.workspace_path), plan.markdown)
    db.commit()
    db.refresh(plan)
    return PlanOut.model_validate(plan)


@router.post("/api/plans/{plan_id}/revise", response_model=PlanOut, status_code=201)
def revise_plan(plan_id: int, body: PlanRevise, db: Session = Depends(get_db)):
    """plan 수정 → 새 세대 DRAFT plan (FR-4.3 — 파생물 직접 수정 없이 plan만 고친다)."""
    base = _plan_or_404(db, plan_id)
    project = db.get(Project, base.project_id)
    try:
        plan = _validate_markdown(body.markdown)
    except PlanError as e:
        raise PlanError(f"plan 포맷 검증 실패 — {e}")

    max_ver = db.scalar(
        select(Plan.version_no).where(Plan.project_id == base.project_id)
        .order_by(Plan.version_no.desc()).limit(1)
    )
    p = Plan(project_id=base.project_id, version_no=(max_ver or 0) + 1,
             markdown=body.markdown, docs=plan.docs,
             parsed_ok=True, status=PlanStatus.DRAFT, origin=PlanOrigin.EDIT)
    db.add(p)
    db.flush()
    write_plan_mirror(Path(project.workspace_path), body.markdown)
    db.commit()
    db.refresh(p)
    return PlanOut.model_validate(p)