# -*- coding: utf-8 -*-
"""검수 API (FR-4) — 리포트 큐 진입·조회.

수정 적용(FR-4.3)은 기존 게이트를 재사용한다: 수동은 plan 탭 revise → 승인 → 재생성,
자동은 POST /api/plans/{plan_id}/revise-from-review job(LLM plan 수정 → 새 DRAFT 세대).
어느 쪽이든 검수는 판단만 하고 SSOT·게이트·채번 구조를 건드리지 않는다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_db
from ..errors import http_404, http_409
from ..models import Build, Derivative, Job, JobType, Plan, PlanStatus, Project
from ..schemas import JobOut

router = APIRouter(prefix="/api/projects/{project_id}/reviews", tags=["reviews"])


class FindingOut(BaseModel):
    code: str
    severity: str
    where: str
    message: str
    suggestion: str | None = None  # LLM 발견사항의 plan 수정 방향 (결정론 발견사항엔 없음)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    plan_id: int
    findings: list[FindingOut]
    red_count: int
    yellow_count: int
    white_count: int
    llm_ok: bool
    summary: str
    created_at: object


@router.post("", status_code=202, response_model=JobOut)
def enqueue_review(project_id: int, db: Session = Depends(get_db),
                   settings: Settings = Depends(get_settings)):
    """최신 승인 plan에 대한 검수 잡을 큐에 넣는다."""
    project = db.get(Project, project_id)
    if project is None:
        raise http_404(f"프로젝트 없음: {project_id}")
    plan = db.scalar(
        select(Plan)
        .where(Plan.project_id == project_id, Plan.status == PlanStatus.APPROVED)
        .order_by(Plan.version_no.desc()).limit(1)
    )
    if plan is None:
        raise http_409("승인된 plan이 없습니다 — 먼저 plan을 승인하세요")
    has_output = db.scalar(
        select(Derivative.id).where(Derivative.project_id == project_id).limit(1)
    )
    if has_output is None:
        raise http_409("검수할 파생물이 없습니다 — 먼저 산출물을 생성하세요")
    job = Job(project_id=project_id, type=JobType.REVIEW,
              payload={"plan_id": plan.id})
    db.add(job)
    db.flush()
    return JobOut.model_validate(job)


@router.get("", response_model=list[ReviewOut])
def list_reviews(project_id: int, db: Session = Depends(get_db)):
    from ..models import ReviewReport
    if db.get(Project, project_id) is None:
        raise http_404(f"프로젝트 없음: {project_id}")
    reports = db.scalars(
        select(ReviewReport).where(ReviewReport.project_id == project_id)
        .order_by(ReviewReport.id.desc())
    ).all()
    return [ReviewOut.model_validate(r) for r in reports]


@router.get("/{review_id}", response_model=ReviewOut)
def get_review(project_id: int, review_id: int, db: Session = Depends(get_db)):
    from ..models import ReviewReport
    r = db.get(ReviewReport, review_id)
    if r is None or r.project_id != project_id:
        raise http_404(f"검수 리포트 없음: {review_id}")
    return ReviewOut.model_validate(r)