# -*- coding: utf-8 -*-
"""plan revise job 핸들러 (FR-4.3) — 검수 발견사항 반영을 워커가 실행한다.

파생물·빌드는 건드리지 않는다 — plan 세대만 추가하고, 승인 게이트·재생성은
기존 게이트(derive_build의 APPROVED 검사)를 그대로 경유한다 (SSOT, 원칙 5).
"""
from __future__ import annotations

from pathlib import Path

from planforge.plan import PlanError

from app.modules.projects.facade import get_project
from app.modules.review.facade import get_report
from app.shared.workspace import write_plan_mirror

from ..facade import PlanOrigin, PlanStatus, create_generation, get_plan
from ..infrastructure.models import Plan
from .planrevise import PlanReviseError, run_plan_revise, validate_plan_markdown


def run_plan_revise_job(ctx, session, job) -> dict:
    """검수 발견사항 반영: LLM plan 수정 → 결정론 검증 → 새 DRAFT 세대."""
    payload = job.payload
    plan = get_plan(session, payload["plan_id"])
    project = get_project(session, job.project_id)
    if plan is None or project is None:
        raise ValueError("plan 또는 project가 없습니다")
    review = get_report(session, payload["review_id"])
    if review is None or review.project_id != job.project_id:
        raise ValueError("검수 리포트가 없습니다")
    if review.plan_id != plan.id:
        raise ValueError("검수 리포트의 plan 세대가 job payload와 다릅니다")

    findings = list(review.findings or [])
    indices = payload.get("finding_indices")
    if indices is None:
        selected = findings
    else:
        selected = [findings[i] for i in indices if 0 <= i < len(findings)]
    if not selected:
        raise PlanError("반영할 발견사항이 없습니다")

    from app.shared.llm import LLMRegistry

    registry = LLMRegistry(ctx.settings.llm_config_path, ctx.llm_overrides)
    try:
        chat_fn = registry.chat_fn("plan_revise")
    except KeyError:
        chat_fn = registry.chat_fn("review")  # 신규 프로필이 없는 기존 config 호환
    md, parsed = run_plan_revise(chat_fn, plan.markdown, selected, review.summary or "")

    validate_plan_markdown(md)  # 이중 방어 — run_plan_revise 내부 검증과 동일 권위
    if md.strip() == (plan.markdown or "").strip():
        raise PlanError("LLM 결과에 변경이 없습니다 — plan 세대를 만들지 않았습니다")

    new_plan = create_generation(session, plan.project_id, markdown=md, docs=parsed.docs,
                                 parsed_ok=True, origin=PlanOrigin.REVIEW)
    # SSOT 미러 — revise_plan과 동일: DRAFT 세대도 미러를 갱신한다
    write_plan_mirror(Path(project.workspace_path), md)
    return {"plan_id": new_plan.id, "version_no": new_plan.version_no,
            "applied_count": len(selected)}