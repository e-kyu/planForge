# -*- coding: utf-8 -*-
"""review job 핸들러 (FR-4) — 결정론(구조·수치·태그·팩트·세대) + LLM 내용 검수.

결정론 검수는 planforge 엔진(numcheck·review)과 이 모듈의 세대 대응 점검이
담당하고, 내용 판단만 LLM에 위임한다 (application/review_agent.py). 어느 쪽
실패도 결정론 결과는 보존한다.
"""
from __future__ import annotations

from pathlib import Path

from planforge.numcheck import check_report, check_slides
from planforge.plan import PlanError, filter_slides, parse_plan_file
from planforge.review import check_doc_tags, check_facts

from app.modules.derivatives.facade import DerivativeKind, list_builds, list_for_plan
from app.modules.facts.facade import list_active_facts
from app.modules.plans.facade import PlanStatus, get_plan
from app.modules.projects.facade import get_project
from app.shared.workspace import write_plan_mirror

from ..infrastructure.models import ReviewReport
from .review_agent import run_llm_review


def run_review(ctx, session, job) -> dict:
    """검수: 결정론(구조·수치·태그·팩트·세대) + LLM 내용 검수 → ReviewReport 1건."""
    payload = job.payload
    project = get_project(session, job.project_id)
    if project is None:
        raise ValueError("project가 없습니다")

    plan = get_plan(session, payload["plan_id"])
    if plan is None:
        raise ValueError("plan이 없습니다")
    if plan.status != PlanStatus.APPROVED:
        from planforge.plan import PlanError
        raise PlanError("승인된 plan만 검수 대상입니다")

    findings: list[dict] = []

    def add(code: str, severity: str, where: str, message: str,
            suggestion: str | None = None) -> None:
        findings.append({"code": code, "severity": severity, "where": where,
                         "message": message, "suggestion": suggestion})

    # SSOT 미러 (Deriver와 동일 — 엔진이 읽는 파일 형태일 뿐)
    ws = Path(project.workspace_path)
    plan_mirror = write_plan_mirror(ws, plan.markdown)
    parsed = parse_plan_file(plan_mirror)

    # 1) 파생물 ↔ plan 대조 (구조 + 수치 무결성 — numcheck)
    # 같은 세대(plan_id 일치) 파생물만 — 이전 세대는 2)의 세대 대응성에서 보고한다
    derivative_docs: list[dict] = []
    derivs = list_for_plan(session, project.id, plan.id)
    latest_by_key: dict[tuple, object] = {}
    for d in derivs:
        latest_by_key[(d.kind, d.doc)] = d  # id 순 — 뒤(최신)가 이김
    for (kind, doc), d in sorted(latest_by_key.items()):
        derivative_docs.append({"doc": doc, "kind": kind.value, "json": d.json})
        slides = filter_slides(parsed.slides, doc)
        f = (check_slides(slides, parsed.key_messages, d.json) if kind == DerivativeKind.SLIDES
             else check_report(slides, parsed.key_messages, d.json))
        for x in f:
            add(x.code, x.severity, x.where, x.message, suggestion=x.suggestion)

    # 2) 세대 대응성 (FR-4.1) — 기존 빌드가 이 plan 세대인지 (채번은 확장자별 독립이므로 plan_id로)
    for b in list_builds(session, project.id):
        if b.plan_id != plan.id:
            add("generation", "red", f"산출물 {b.title}_v{b.version_no:02d}.{b.ext}",
                "이전 plan 세대의 산출물입니다 — plan을 고친 뒤 파생물을 재생성하세요 (재생성 대상)")

    # 3) 문서 태그 검수
    for x in check_doc_tags(parsed):
        add(x.code, x.severity, x.where, x.message, suggestion=x.suggestion)

    # 4) 팩트 대조 (FR-4.4 전제 — 활성 팩트만)
    facts = [{"content": f.content, "source": f.source, "date": f.date.isoformat()}
             for f in list_active_facts(session, project.id)]
    for x in check_facts(parsed, facts):
        add(x.code, x.severity, x.where, x.message, suggestion=x.suggestion)

    # 5) LLM 내용 검수 (실패해도 결정론 결과는 보존)
    llm_ok = True
    summary = ""
    try:
        from app.shared.llm import LLMRegistry
        registry = LLMRegistry(ctx.settings.llm_config_path, ctx.llm_overrides)
        lf, summary, llm_ok = run_llm_review(
            registry.chat_fn("review"), plan.markdown, derivative_docs, facts)
        findings.extend(lf)
    except Exception as e:  # noqa: BLE001 — 내용 검수 실패는 리포트를 막지 않는다
        llm_ok = False
        add("llm-review", "yellow", "내용 검수", f"LLM 내용 검수 실패: {e}")
    if not llm_ok and not any(f["code"] == "llm-review" for f in findings):
        add("llm-review", "yellow", "내용 검수",
            "LLM 내용 검수가 도구 호출 없이 종료됐습니다 — 결정론 검수 결과만 반영됨")

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