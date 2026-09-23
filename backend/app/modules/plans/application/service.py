# -*- coding: utf-8 -*-
"""plan 세대 유스케이스 — 승인 게이트·수정 게이트 (FR-2.8/2.9, FR-4.3).

원칙 1(SSOT): 콘텐츠 원본은 DB plans.markdown. workspaces/*/plan.md는
미러이며 파생물 생성은 항상 이 원본에서 재생성된다.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.interview.facade import complete_plan_review_sessions
from app.modules.projects.facade import require_project
from app.shared.errors import http_409
from app.shared.workspace import write_plan_mirror

from ..facade import PlanOrigin, PlanStatus, create_generation, require_plan
from ..infrastructure.models import Plan
from .planrevise import validate_plan_markdown


def approve_plan(db: Session, plan_id: int) -> Plan:
    """승인 게이트 (FR-2.9) — 승인 전에 파생 단계로 넘어가지 않는다."""
    plan = require_plan(db, plan_id)
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

    # plan을 작성한 세션 완료 처리 (interview 모듈 경유)
    complete_plan_review_sessions(db, plan.project_id)

    project = require_project(db, plan.project_id)
    write_plan_mirror(Path(project.workspace_path), plan.markdown)
    db.commit()
    db.refresh(plan)
    return plan


def revise_plan(db: Session, plan_id: int, markdown: str) -> Plan:
    """plan 수정 → 새 세대 DRAFT plan (FR-4.3 — 파생물 직접 수정 없이 plan만 고친다)."""
    from planforge.plan import PlanError

    base = require_plan(db, plan_id)
    project = require_project(db, base.project_id)
    try:
        parsed = validate_plan_markdown(markdown)
    except PlanError as e:
        raise PlanError(f"plan 포맷 검증 실패 — {e}")

    p = create_generation(db, base.project_id, markdown=markdown, docs=parsed.docs,
                          parsed_ok=True, origin=PlanOrigin.EDIT)
    write_plan_mirror(Path(project.workspace_path), markdown)
    db.commit()
    db.refresh(p)
    return p