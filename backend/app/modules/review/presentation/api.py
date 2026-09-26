# -*- coding: utf-8 -*-
"""검수 API (FR-4) — 리포트 큐 진입·조회.

수정 적용(FR-4.3)은 기존 게이트를 재사용한다: 수동은 plan 탭 revise → 승인 → 재생성,
자동은 POST /api/plans/{plan_id}/revise-from-review job(LLM plan 수정 → 새 DRAFT 세대).
어느 쪽이든 검수는 판단만 하고 SSOT·게이트·채번 구조를 건드리지 않는다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.derivatives.facade import has_any
from app.modules.jobs.facade import JobType, enqueue
from app.modules.jobs.presentation.schemas import JobOut
from app.modules.plans.facade import latest_approved
from app.modules.projects.facade import require_project
from app.shared.db import get_db
from app.shared.errors import http_404, http_409

from ..facade import get_report
from ..infrastructure.models import ReviewReport
from .schemas import ReviewOut

router = APIRouter(prefix="/api/projects/{project_id}/reviews", tags=["reviews"])


@router.post("", status_code=202, response_model=JobOut)
def enqueue_review(project_id: int, db: Session = Depends(get_db)):
    """최신 승인 plan에 대한 검수 잡을 큐에 넣는다."""
    require_project(db, project_id)
    plan = latest_approved(db, project_id)
    if plan is None:
        raise http_409("승인된 plan이 없습니다 — 먼저 plan을 승인하세요")
    if not has_any(db, project_id):
        raise http_409("검수할 파생물이 없습니다 — 먼저 산출물을 생성하세요")
    job = enqueue(db, project_id, JobType.REVIEW, {"plan_id": plan.id})
    return JobOut.model_validate(job)


@router.get("", response_model=list[ReviewOut])
def list_reviews(project_id: int, db: Session = Depends(get_db)):
    require_project(db, project_id)
    reports = db.scalars(
        select(ReviewReport).where(ReviewReport.project_id == project_id)
        .order_by(ReviewReport.id.desc())
    ).all()
    return [ReviewOut.model_validate(r) for r in reports]


@router.get("/{review_id}", response_model=ReviewOut)
def get_review(project_id: int, review_id: int, db: Session = Depends(get_db)):
    r = get_report(db, review_id)
    if r is None or r.project_id != project_id:
        raise http_404(f"검수 리포트 없음: {review_id}")
    return ReviewOut.model_validate(r)