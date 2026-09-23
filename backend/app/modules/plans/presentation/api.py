# -*- coding: utf-8 -*-
"""plan.md API (FR-2.8/2.9) — plan 세대 조회·승인·수정 게이트."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.jobs.facade import JobType, enqueue
from app.modules.jobs.presentation.schemas import JobOut
from app.modules.projects.facade import require_project
from app.modules.review.facade import get_report
from app.shared.db import get_db
from app.shared.errors import http_404, http_409

from ..application import service
from ..facade import require_plan
from ..infrastructure.models import Plan
from .schemas import PlanOut, PlanRevise, PlanReviseFromReview

router = APIRouter(tags=["plans"])


@router.get("/api/projects/{project_id}/plans", response_model=list[PlanOut])
def list_plans(project_id: int, db: Session = Depends(get_db)):
    require_project(db, project_id)
    plans = db.scalars(
        select(Plan).where(Plan.project_id == project_id).order_by(Plan.version_no)
    )
    return [PlanOut.model_validate(p) for p in plans]


@router.get("/api/plans/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    return PlanOut.model_validate(require_plan(db, plan_id))


@router.post("/api/plans/{plan_id}/approve", response_model=PlanOut)
def approve_plan(plan_id: int, db: Session = Depends(get_db)):
    """승인 게이트 (FR-2.9) — 승인 전에 파생 단계로 넘어가지 않는다."""
    plan = service.approve_plan(db, plan_id)
    return PlanOut.model_validate(plan)


@router.post("/api/plans/{plan_id}/revise", response_model=PlanOut, status_code=201)
def revise_plan(plan_id: int, body: PlanRevise, db: Session = Depends(get_db)):
    """plan 수정 → 새 세대 DRAFT plan (FR-4.3 — 파생물 직접 수정 없이 plan만 고친다)."""
    plan = service.revise_plan(db, plan_id, body.markdown)
    return PlanOut.model_validate(plan)


@router.post("/api/plans/{plan_id}/revise-from-review", status_code=202,
             response_model=JobOut)
def revise_plan_from_review(plan_id: int, body: PlanReviseFromReview,
                            db: Session = Depends(get_db)):
    """검수 발견사항 → LLM plan 수정 job (FR-4.3).

    동기 LLM 호출이 아니라 job 큐로 간다 (derive/review와 동일 — LLM 지연 흡수).
    워커가 포맷 검증 게이트를 통과한 plan만 새 DRAFT 세대로 만들며, 승인 게이트와
    파생물 재생성은 기존 게이트를 그대로 경유한다.
    """
    plan = require_plan(db, plan_id)
    r = get_report(db, body.review_id)
    if r is None or r.project_id != plan.project_id:
        raise http_404(f"검수 리포트 없음: {body.review_id}")
    if r.plan_id != plan_id:
        raise http_409("검수 리포트의 plan 세대가 다릅니다 — 검수 대상 세대의 plan에 반영하세요")

    findings = list(r.findings or [])
    if body.finding_indices is None:
        indices = list(range(len(findings)))
    else:
        indices = body.finding_indices
        if len(set(indices)) != len(indices):
            raise http_409("finding_indices에 중복이 있습니다")
        for i in indices:
            if not 0 <= i < len(findings):
                raise http_409(f"finding 인덱스가 범위 밖입니다: {i} (0..{len(findings) - 1})")
    if not indices:
        raise http_409("반영할 발견사항이 선택되지 않았습니다")

    job = enqueue(db, plan.project_id, JobType.PLAN_REVISE,
                  {"plan_id": plan_id, "review_id": body.review_id,
                   "finding_indices": indices})
    return JobOut.model_validate(job)