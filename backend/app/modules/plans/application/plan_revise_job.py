# -*- coding: utf-8 -*-
"""plan revise job 핸들러 (FR-4.3) — 검수 발견사항 반영을 워커가 실행한다.

파생물·빌드는 건드리지 않는다 — plan 세대만 추가하고, 승인 게이트·재생성은
기존 게이트(derive_build의 APPROVED 검사)를 그대로 경유한다 (SSOT, 원칙 5).

단일 책임 분해: 컨텍스트 로드·세대 일치 검사 → 발견사항 선택(조용한 범위 필터) →
LLM 반영 → 이중 검증·무변경 판정·새 세대 영속. 진행 기록 시점에 대기 중인 도메인
행이 없다 (create_generation은 이후) — facade 커밋 계약 충족.
"""
from __future__ import annotations

from planforge.plan import PlanError

from app.modules.jobs.facade import report_progress_safe
from app.modules.projects.facade import get_project
from app.modules.review.facade import get_report
from app.shared.workspace import write_plan_mirror

from ..facade import PlanOrigin, create_generation, get_plan
from .planrevise import run_plan_revise, validate_plan_markdown
from .service import _mirror_root


def run_plan_revise_job(ctx, session, job) -> dict:
    """검수 발견사항 반영: LLM plan 수정 → 결정론 검증 → 새 DRAFT 세대."""
    plan, project, review = _load_context(session, job)
    selected = _select_findings(job.payload, review)
    md, parsed = _run_llm(ctx, session, job, plan, selected, review.summary or "")
    return _persist_new_generation(session, plan, project, md, parsed, selected)


def _load_context(session, job) -> tuple:
    """plan/project/review 조회 + 검수 리포트 세대 일치 검사."""
    plan = get_plan(session, job.payload["plan_id"])
    project = get_project(session, job.project_id)
    if plan is None or project is None:
        raise ValueError("plan 또는 project가 없습니다")
    review = get_report(session, job.payload["review_id"])
    if review is None or review.project_id != job.project_id:
        raise ValueError("검수 리포트가 없습니다")
    if review.plan_id != plan.id:
        raise ValueError("검수 리포트의 plan 세대가 job payload와 다릅니다")
    return plan, project, review


def _select_findings(payload: dict, review) -> list[dict]:
    """반영할 발견사항 — finding_indices 미지정이면 전체.

    범위를 벗어난 인덱스는 **조용히 버린다** — API의 409 정책과 의도적으로 다른
    워커 정책이다(큐 진입 후 리포트 변동 대비). 선택이 비면 실패로 기록한다.
    """
    findings = list(review.findings or [])
    indices = payload.get("finding_indices")
    if indices is None:
        selected = findings
    else:
        selected = [findings[i] for i in indices if 0 <= i < len(findings)]
    if not selected:
        raise PlanError("반영할 발견사항이 없습니다")
    return selected


def _run_llm(ctx, session, job, plan, selected: list[dict], summary: str):
    """LLM 반영 — plan_revise 프로필, 없으면 review로 폴백 (기존 config 호환)."""
    def on_attempt(n: int, max_n: int) -> None:
        report_progress_safe(session, job, "llm", log_tag="plan_revise",
                             attempt=n, max_attempts=max_n)

    from app.shared.llm import LLMRegistry

    # 초기 진행 기록 — DB 오류가 작업 자체를 죽이지 않게 방어한다 (facade 계약: caller 방어).
    report_progress_safe(session, job, "llm", log_tag="plan_revise")
    registry = LLMRegistry(ctx.settings.llm_config_path, ctx.llm_overrides)
    try:
        chat_fn = registry.chat_fn("plan_revise")
    except KeyError:
        chat_fn = registry.chat_fn("review")  # 신규 프로필이 없는 기존 config 호환
    return run_plan_revise(chat_fn, plan.markdown, selected, summary,
                           on_attempt=on_attempt)


def _persist_new_generation(session, plan, project, md: str, parsed, selected: list[dict]) -> dict:
    """결정론 이중 검증 → 무변경 판정 → 새 DRAFT 세대 + SSOT 미러."""
    validate_plan_markdown(md)  # 이중 방어 — run_plan_revise 내부 검증과 동일 권위
    if md.strip() == (plan.markdown or "").strip():
        raise PlanError("LLM 결과에 변경이 없습니다 — plan 세대를 만들지 않았습니다")

    new_plan = create_generation(session, plan.project_id, markdown=md, docs=parsed.docs,
                                 parsed_ok=True, origin=PlanOrigin.REVIEW,
                                 doc_slug=plan.doc_slug)
    # SSOT 미러 — revise_plan과 동일: DRAFT 세대도 미러를 갱신한다 (문서 plan은
    # 문서별 하위 경로 — job 세션에서 has_doc_layout을 판정한다)
    write_plan_mirror(_mirror_root(session, plan.project_id, project.workspace_path,
                                   plan.doc_slug), md)
    return {"plan_id": new_plan.id, "version_no": new_plan.version_no,
            "applied_count": len(selected)}
