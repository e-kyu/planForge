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

from app.modules.docloops import facade as docloops
from app.modules.interview.facade import complete_plan_review_sessions
from app.modules.projects.facade import require_project
from app.shared.errors import http_409
from app.shared.workspace import doc_ws_root, ensure_doc_ws, write_plan_mirror

from ..facade import PlanOrigin, PlanStatus, create_generation, require_plan
from ..infrastructure.models import Plan
from .planrevise import validate_plan_markdown


def _mirror_root(db: Session, project_id: int, workspace_path, doc_slug: str | None):
    """plan 미러를 쓸 ws 루트 — 문서 plan은 문서별 하위, 레거시(None) plan은 루트.

    레이아웃 권위는 doc_loops 행(has_doc_layout) — 행 없는(레거시) 프로젝트의 doc
    plan도 루트 경로를 유지한다 (step 4 agent._mirror_root와 동일 규칙). 지연 생성이
    없는 경로(직접 시드 plan의 승인)에서도 미러 쓰기가 성립하도록 하위 구조를
    멱등 생성한다 (ensure_doc_ws — 기존 디렉터리는 그대로).
    """
    root = doc_ws_root(Path(workspace_path), doc_slug,
                       doc_layout=docloops.has_doc_layout(db, project_id))
    return ensure_doc_ws(root)


def _scoped_supersede(db: Session, plan: Plan) -> None:
    """이전 승인본은 문서 스코프 내 세대 교체 — 유효한 SSOT 승인본은 문서당 최신 하나.

    레거시(None) plan은 NULL 스코프로 좁힌다 — SQL equality로는 NULL이 매칭되지
    않으므로 is_(None) 명시 분기가 필수다. 그렇지 않으면 레거시 승인본이 SUPERSEDED로
    전이되지 않는다. 효과: proposal 승인본이 유지되는 상태에서 uiux plan 승인이
    가능하고, 문서별로는 승인본 1개 불변식이 유지된다.
    """
    q = select(Plan).where(
        Plan.project_id == plan.project_id, Plan.status == PlanStatus.APPROVED)
    if plan.doc_slug is None:
        q = q.where(Plan.doc_slug.is_(None))
    else:
        q = q.where(Plan.doc_slug == plan.doc_slug)
    for old in db.scalars(q).all():
        old.status = PlanStatus.SUPERSEDED


def approve_plan(db: Session, plan_id: int) -> Plan:
    """승인 게이트 (FR-2.9) — 승인 전에 파생 단계로 넘어가지 않는다."""
    plan = require_plan(db, plan_id)
    if plan.status != PlanStatus.DRAFT:
        raise http_409(f"DRAFT plan만 승인할 수 있습니다 (현재 {plan.status.value})")

    _scoped_supersede(db, plan)
    plan.status = PlanStatus.APPROVED
    plan.approved_at = datetime.now(timezone.utc)

    # plan을 작성한 세션 완료 처리 (interview 모듈 경유) — 문서 plan이면 그 문서
    # 세션만 완료한다 (step 4 narrowing). 레거시(None) plan은 파라미터 없이 전체
    # (기존 계약).
    if plan.doc_slug is None:
        complete_plan_review_sessions(db, plan.project_id)
    else:
        complete_plan_review_sessions(db, plan.project_id, doc_slug=plan.doc_slug)

    project = require_project(db, plan.project_id)
    write_plan_mirror(_mirror_root(db, plan.project_id, project.workspace_path,
                                   plan.doc_slug), plan.markdown)

    # 루프 진행 훅 — 승인 커밋 전 이 트랜잭션 안에서 (자기 문서 done + 다음 문서
    # 활성화 래치). 행 없는(레거시) 프로젝트는 facade가 no-op — 기존 프로젝트 안전.
    docloops.on_plan_approved(db, plan.project_id, plan.doc_slug)

    db.commit()
    db.refresh(plan)
    return plan


def revise_plan(db: Session, plan_id: int, markdown: str) -> Plan:
    """plan 수정 → 새 세대 DRAFT plan (FR-4.3 — 파생물 직접 수정 없이 plan만 고친다)."""
    base = require_plan(db, plan_id)
    project = require_project(db, base.project_id)
    # 검증·라벨링은 validate_plan_markdown(단일 권위)의 소관 — 여기서 다시 감싸면
    # 라벨이 겹친다. PlanError → 422 매핑은 전역 핸들러(shared/errors.py)가 한다.
    parsed = validate_plan_markdown(markdown)

    p = create_generation(db, base.project_id, markdown=markdown, docs=parsed.docs,
                          parsed_ok=True, origin=PlanOrigin.EDIT, doc_slug=base.doc_slug)
    write_plan_mirror(_mirror_root(db, base.project_id, project.workspace_path,
                                   base.doc_slug), markdown)
    db.commit()
    db.refresh(p)
    return p