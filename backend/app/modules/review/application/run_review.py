# -*- coding: utf-8 -*-
"""review job 핸들러 (FR-4) — 결정론(구조·수치·태그·팩트·세대) + LLM 내용 검수.

결정론 검수는 planforge 엔진(numcheck·review)과 이 모듈의 세대 대응 점검이
담당하고, 내용 판단만 LLM에 위임한다 (application/review_agent.py). 어느 쪽
실패도 결정론 결과는 보존한다.

단일 책임 분해: 컨텍스트 로드 → 파생물 대조 → 세대 대응 → 태그·팩트 → LLM 검수 →
리포트 조립. 진행 기록 시점에는 대기 중인 도메인 행이 없다 (findings는 로컬 리스트,
ReviewReport는 마지막에 add) — facade 커밋 계약 충족.
"""
from __future__ import annotations

from dataclasses import asdict

from planforge.numcheck import check_report, check_slides
from planforge.plan import PlanError, filter_slides, parse_plan_file
from planforge.review import check_doc_tags, check_facts

from app.modules.docloops import facade as docloops
from app.modules.derivatives.facade import DerivativeKind, list_builds, list_for_plan
from app.modules.facts.facade import list_active_facts
from app.modules.jobs.facade import report_progress_safe
from app.modules.plans.facade import PlanStatus, get_plan
from app.modules.projects.facade import get_project
from app.shared.collections import latest_by_key
from app.shared.workspace import write_plan_mirror

from ..infrastructure.models import ReviewReport
from .review_agent import run_llm_review


def run_review(ctx, session, job) -> dict:
    """검수: 결정론(구조·수치·태그·팩트·세대) + LLM 내용 검수 → ReviewReport 1건."""
    project, plan, parsed = _load_context(session, job)

    deriv_findings, derivative_docs = _check_derivative_docs(session, project, plan, parsed)
    gen_findings = _check_generation(session, project, plan)
    tag_findings, facts = _check_tags_and_facts(session, project, parsed)
    findings = [*deriv_findings, *gen_findings, *tag_findings]

    llm_ok, summary = _run_llm_review(ctx, session, job, plan, derivative_docs, facts, findings)
    return _build_report(session, project, plan, findings, llm_ok, summary)


def _finding(code: str, severity: str, where: str, message: str,
             suggestion: str | None = None) -> dict:
    """발견사항 dict — 키 순서 `code, severity, where, message, suggestion` 고정."""
    return {"code": code, "severity": severity, "where": where,
            "message": message, "suggestion": suggestion}


def _load_context(session, job) -> tuple:
    """project/plan 조회 + 승인 게이트, 문서별 ws + SSOT 미러 기록 → 파싱 결과."""
    project = get_project(session, job.project_id)
    if project is None:
        raise ValueError("project가 없습니다")

    plan = get_plan(session, job.payload["plan_id"])
    if plan is None:
        raise ValueError("plan이 없습니다")
    if plan.status != PlanStatus.APPROVED:
        raise PlanError("승인된 plan만 검수 대상입니다")

    # SSOT 미러 (Deriver와 동일 — 엔진이 읽는 파일 형태일 뿐). 문서 plan은 그 문서의
    # ws 하위에 기록된 미러를 대조한다 (plans 승인·derive와 동일 경로 규칙 —
    # docloops.resolve_workspace_root에 위임, ensure=True로 하위 구조를 멱등 생성).
    mirror_root = docloops.resolve_workspace_root(
        session, project.id, project.workspace_path, plan.doc_slug, ensure=True)
    plan_mirror = write_plan_mirror(mirror_root, plan.markdown)
    return project, plan, parse_plan_file(plan_mirror)


def _check_derivative_docs(session, project, plan, parsed) -> tuple[list[dict], list[dict]]:
    """1) 파생물 ↔ plan 대조 (구조 + 수치 무결성 — numcheck).

    같은 세대(plan_id 일치) 파생물만 — 이전 세대는 세대 대응성에서 보고한다.
    list_for_plan은 id 오름차순이므로 뒤집어 latest_by_key(첫 행)에 넘기면
    같은 (kind, doc)의 최신(마지막) 행이 남는다.
    """
    derivative_docs: list[dict] = []
    out: list[dict] = []
    derivs = list_for_plan(session, project.id, plan.id)
    latest = latest_by_key(reversed(derivs), lambda d: (d.kind, d.doc))
    for (kind, doc), d in sorted(latest.items()):
        derivative_docs.append({"doc": doc, "kind": kind.value, "json": d.json})
        slides = filter_slides(parsed.slides, doc)
        f = (check_slides(slides, parsed.key_messages, d.json) if kind == DerivativeKind.SLIDES
             else check_report(slides, parsed.key_messages, d.json))
        out.extend(asdict(x) for x in f)
    return out, derivative_docs


def _check_generation(session, project, plan) -> list[dict]:
    """2) 세대 대응성 (FR-4.1) — 기존 빌드가 이 plan 세대인지 (채번은 확장자별 독립).

    이 plan이 문서 plan이면 그 문서의 빌드만 대상으로 좁힌다 — 다른 문서의 산출물은
    이 plan 세대의 재생성 대상이 아니므로(각자 문서별 ws에 채번됨) red 오탐이 된다.
    레거시(None) plan은 기존 계약대로 전체 빌드를 대조한다.
    """
    out: list[dict] = []
    for b in list_builds(session, project.id):
        if plan.doc_slug is not None and b.doc_slug != plan.doc_slug:
            continue
        if b.plan_id != plan.id:
            out.append(_finding(
                "generation", "red", f"산출물 {b.title}_v{b.version_no:02d}.{b.ext}",
                "이전 plan 세대의 산출물입니다 — plan을 고친 뒤 파생물을 재생성하세요 (재생성 대상)"))
    return out


def _check_tags_and_facts(session, project, parsed) -> tuple[list[dict], list[dict]]:
    """3) 문서 태그 검수 + 4) 팩트 대조 (FR-4.4 전제 — 활성 팩트만)."""
    out = [asdict(x) for x in check_doc_tags(parsed)]
    facts = [{"content": f.content, "source": f.source, "date": f.date.isoformat()}
             for f in list_active_facts(session, project.id)]
    out.extend(asdict(x) for x in check_facts(parsed, facts))
    return out, facts


def _run_llm_review(ctx, session, job, plan, derivative_docs, facts,
                    findings: list[dict]) -> tuple[bool, str]:
    """5) LLM 내용 검수 (실패해도 결정론 결과는 보존) — findings에 직접 덧붙인다.

    진행 기록의 DB 오류가 LLM 검수 실패로 오기록되지 않도록 report_progress_safe를
    쓴다 (facade 계약: caller 방어).
    """
    def on_attempt(n: int, max_n: int) -> None:
        report_progress_safe(session, job, "llm", log_tag="review",
                             attempt=n, max_attempts=max_n)

    llm_ok = True
    summary = ""
    try:
        from app.shared.llm import LLMRegistry
        report_progress_safe(session, job, "llm", log_tag="review")
        registry = LLMRegistry(ctx.settings.llm_config_path, ctx.llm_overrides)
        lf, summary, llm_ok = run_llm_review(
            registry.chat_fn("review"), plan.markdown, derivative_docs, facts,
            on_attempt=on_attempt)
        findings.extend(lf)
    except Exception as e:  # noqa: BLE001 — 내용 검수 실패는 리포트를 막지 않는다
        llm_ok = False
        findings.append(_finding("llm-review", "yellow", "내용 검수",
                                 f"LLM 내용 검수 실패: {e}"))
    if not llm_ok and not any(f["code"] == "llm-review" for f in findings):
        findings.append(_finding(
            "llm-review", "yellow", "내용 검수",
            "LLM 내용 검수가 도구 호출 없이 종료됐습니다 — 결정론 검수 결과만 반영됨"))
    return llm_ok, summary


def _build_report(session, project, plan, findings: list[dict],
                  llm_ok: bool, summary: str) -> dict:
    """counts + ReviewReport add/flush + job.result dict."""
    counts = {"red": sum(1 for f in findings if f["severity"] == "red"),
              "yellow": sum(1 for f in findings if f["severity"] == "yellow"),
              "white": sum(1 for f in findings if f["severity"] == "white")}
    report = ReviewReport(
        project_id=project.id, plan_id=plan.id, findings=findings,
        red_count=counts["red"], yellow_count=counts["yellow"],
        white_count=counts["white"], llm_ok=llm_ok, summary=summary,
    )
    session.add(report)
    session.flush()
    return {"review_id": report.id, "counts": counts}
