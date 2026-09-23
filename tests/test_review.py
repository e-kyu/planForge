# -*- coding: utf-8 -*-
"""검수 에이전트 테스트 (FR-4) — 결정론 검수 엔진 + review 잡 + API 게이트."""
from __future__ import annotations

from fakes import FakeLLM, correct_report_payload, correct_slides_payload, plan_sample_markdown, tool_call

from planforge.plan.parser import parse_plan_text
from planforge.review import check_doc_tags, check_facts

# ---------------------------------------------------------------- 결정론 엔진

MULTIDOC_PLAN = """# 제안서 기획 (다문서 샘플)

## 메타
- 산출 문서: 제안서, 개발설계서
- 목적: 테스트
- 청중: CTO
- 예상 분량: 5장

## 핵심 메시지 (3개)
1. 매출 12.4억 원
2. 고객 47개사
3. 목표 15.0억 원

## 슬라이드 목록

### 1. [유형: 표지][문서: 제안서] 제안 표지
- 핵심문장: 표지 문장
- 근거/출처: (미확정)

### 2. [유형: 목차][문서: 제안서] 제안 목차
- 핵심문장: 01 현황 / 02 구성 / 03 요청

### 3. [유형: 표][문서: 제안서] 현황
- 근거/출처: 사내 집계
- 표: [지표 | 수치]
  - 매출 | 12.4억 원

### 4. [유형: 마무리][문서: 제안서] 제안 마무리
- 핵심문장: 요청 문장

### 5. [유형: 표지][문서: 개발설계서] 설계서 표지
- 핵심문장: 설계 표지
- 근거/출처: 요구사항 명세

### 6. [유형: 목차][문서: 개발설계서] 설계 목차
- 핵심문장: 01 구성 / 02 데이터 / 03 일정

### 7. [유형: 구성][문서: 개발설계서] 시스템 구성
- 근거/출처: (미확정)
- 구성:
  - 사용자 계층 | 화면 A, 화면 B
  - 데이터 계층 | 보고 DB

### 8. [유형: 마무리][문서: 개발설계서] 설계 마무리
- 핵심문장: 설계 마무리 문장
"""


def test_doc_tags_unknown_tag_is_red():
    plan = parse_plan_text(MULTIDOC_PLAN)
    plan.slides[0].docs.append("없는문서")
    out = check_doc_tags(plan)
    assert any(f.severity == "red" and "없는문서" in f.message for f in out)


def test_doc_tags_toc_mismatch_and_renumber():
    plan = parse_plan_text(MULTIDOC_PLAN)
    # 제안서 목차: 불릿 3개 ↔ 내용 슬라이드 1개 (표 1개) → 누락 참조 + 라벨 정상이므로 불일치 1건
    out = check_doc_tags(plan)
    toc_finds = [f for f in out if f.code == "doc-toc"]
    assert any("불릿 3개 vs 내용 슬라이드 1개" in f.message for f in toc_finds)
    # 라벨은 01..03 재채번 정합 → 재채번 위반은 없어야 한다
    assert not any("재채번이 아닙니다" in f.message for f in toc_finds)
    # 개발설계서: 불릿 3개 ↔ 내용 1개(구성) → 동일하게 1건
    assert sum(1 for f in toc_finds if "'개발설계서'" in f.where) == 1


def test_doc_tags_bad_renumber_is_yellow():
    plan = parse_plan_text(MULTIDOC_PLAN)
    plan.slides[1].message = "02 현황, 05 구성, 99 요청"  # 라벨 02/05/99
    out = check_doc_tags(plan)
    assert any("재채번이 아닙니다" in f.message for f in out)


def test_facts_missing_numeric_is_red():
    plan = parse_plan_text(MULTIDOC_PLAN)
    out = check_facts(plan, [{"content": "4분기 목표 매출 15.0억 원 (출처: 사업계획서)",
                              "source": "사업계획서", "date": "2026-09-18"}])
    assert any(f.severity == "red" and "15.0" in f.message for f in out)


def test_facts_unconfirmed_resolvable_is_yellow():
    # plan에 있는 수치(12.4)를 팩트가 갖고 있으면 해소 제안(yellow)이 나온다
    plan = parse_plan_text(MULTIDOC_PLAN)
    plan.slides[6].message = "(미확정) 매출 12.4억 원 규모"
    out = check_facts(plan, [{"content": "3분기 매출 12.4억 원 (출처: 사내 집계)",
                              "source": "사내 집계", "date": "2026-09-18"}])
    assert any(f.code == "unconfirmed-resolvable" for f in out)


# ---------------------------------------------------------------- review 잡 + API

def _approved_plan(app, project_id: int) -> int:
    from app.modules.plans.infrastructure.models import Plan, PlanOrigin, PlanStatus
    from app.shared.db import make_session_factory

    with make_session_factory(app.state.settings.database_url)() as s:
        plan = Plan(project_id=project_id, version_no=1,
                    markdown=plan_sample_markdown(), docs=["제안서"],
                    parsed_ok=True, status=PlanStatus.APPROVED, origin=PlanOrigin.EDIT)
        s.add(plan)
        s.commit()
        return plan.id


def _run_queue(app, llm, profile="derive"):
    from app.shared.config import get_settings
    from app.shared.db import make_session_factory
    from app.modules.jobs.application.worker import JobContext, claim_next_job, run_job

    ctx = JobContext(
        session_factory=make_session_factory(app.state.settings.database_url),
        settings=get_settings(),
        llm_overrides={profile: llm},
    )
    s = ctx.session_factory()
    try:
        job = claim_next_job(s)
        if job is not None:
            run_job(ctx, job)
    finally:
        s.close()


def test_review_requires_approved_plan(client, app):
    client.post("/api/projects", json={"slug": "rev-gate", "title": "x"})
    r = client.post("/api/projects/1/reviews")
    assert r.status_code == 409


def test_review_requires_derivatives(client, app):
    client.post("/api/projects", json={"slug": "rev-nod", "title": "x"})
    _approved_plan(app, 1)
    r = client.post("/api/projects/1/reviews")
    assert r.status_code == 409


def test_review_job_end_to_end(client, app):
    from app.shared.db import make_session_factory

    client.post("/api/projects", json={"slug": "rev-full", "title": "x"})
    plan_id = _approved_plan(app, 1)

    # 파생물 2종 생성 (fake LLM)
    r = client.post("/api/projects/1/derivatives", json={"kind": "slides"})
    assert r.status_code == 202
    _run_queue(app, FakeLLM([tool_call("write_slides_json", correct_slides_payload())]))
    r = client.post("/api/projects/1/derivatives", json={"kind": "report", "fmts": ["md"]})
    _run_queue(app, FakeLLM([tool_call("write_report_json", correct_report_payload())]))

    # 검수 큐 진입 → 실행 (review 프로필 fake LLM: 발견사항 2건 보고)
    r = client.post("/api/projects/1/reviews")
    assert r.status_code == 202
    job_id = r.json()["id"]
    findings = [
        {"severity": "red", "code": "fabrication", "where": "report.json 섹션 1",
         "message": "plan에 없는 주장이 추가되었다"},
        {"severity": "yellow", "code": "style", "where": "슬라이드 3 (표)",
         "message": "문체가 불일치한다"},
    ]
    _run_queue(app, FakeLLM([tool_call("report_findings",
                                       {"summary": "총평", "findings": findings})]),
               profile="review")

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "done", job
    reports = client.get("/api/projects/1/reviews").json()
    assert len(reports) == 1 and reports[0]["plan_id"] == plan_id
    rep = reports[0]
    assert rep["summary"] == "총평"
    codes = [f["code"] for f in rep["findings"]]
    assert "fabrication" in codes and "style" in codes
    assert rep["red_count"] >= 1 and rep["yellow_count"] >= 1


def test_review_detects_injected_numeric_distortion(client, app):
    """수용 기준 (요청서 §7-3): 파생물에 수치 왜곡을 주입하면 검수가 🔴로 탐지한다."""
    import copy

    from app.shared.db import make_session_factory
    from app.modules.derivatives.infrastructure.models import Derivative, DerivativeKind

    client.post("/api/projects", json={"slug": "rev-distort", "title": "x"})
    _approved_plan(app, 1)

    r = client.post("/api/projects/1/derivatives", json={"kind": "slides"})
    _run_queue(app, FakeLLM([tool_call("write_slides_json", correct_slides_payload())]))
    assert client.get(f"/api/jobs/{r.json()['id']}").json()["status"] == "done"

    # 수치 왜곡 주입 — plan에 없는 13.5로 교체 (테스트 전용 주입, 앱 경로 아님)
    with make_session_factory(app.state.settings.database_url)() as s:
        d = s.query(Derivative).filter(
            Derivative.project_id == 1, Derivative.kind == DerivativeKind.SLIDES).one()
        doc = copy.deepcopy(d.json)
        cover = doc["slides"][0]
        cover["subtitle"] = cover["subtitle"].replace("11.5", "13.5")
        d.json = doc
        s.commit()

    r = client.post("/api/projects/1/reviews")
    _run_queue(app, FakeLLM([tool_call("report_findings", {"summary": "", "findings": []})]),
               profile="review")

    reports = client.get("/api/projects/1/reviews").json()
    num_finds = [f for f in reports[0]["findings"] if f["code"] == "numeric-extra"]
    assert num_finds and num_finds[0]["severity"] == "red"
    assert "13.5" in num_finds[0]["message"]
    assert reports[0]["red_count"] >= 1


def test_review_reports_stale_generation(client, app):
    """이전 세대 빌드가 남아 있으면 red로 보고한다 (FR-4.1 세대 대응성)."""
    from app.shared.db import make_session_factory
    from app.modules.derivatives.infrastructure.models import Build, Derivative, DerivativeKind

    client.post("/api/projects", json={"slug": "rev-gen", "title": "x"})
    plan_id = _approved_plan(app, 1)

    r = client.post("/api/projects/1/derivatives", json={"kind": "slides"})
    _run_queue(app, FakeLLM([tool_call("write_slides_json", correct_slides_payload())]))
    assert client.get(f"/api/jobs/{r.json()['id']}").json()["status"] == "done"

    # plan 세대 교체 — 새 승인 plan을 만들어 build를 '이전 세대'로 만든다
    from app.modules.plans.infrastructure.models import Plan, PlanOrigin, PlanStatus
    with make_session_factory(app.state.settings.database_url)() as s:
        plan2 = Plan(project_id=1, version_no=2,
                     markdown=plan_sample_markdown(), docs=["제안서"],
                     parsed_ok=True, status=PlanStatus.APPROVED, origin=PlanOrigin.EDIT)
        s.add(plan2)
        s.commit()
        new_plan_id = plan2.id

    r = client.post("/api/projects/1/reviews")
    _run_queue(app, FakeLLM([tool_call("report_findings", {"summary": "", "findings": []})]),
               profile="review")

    reports = client.get("/api/projects/1/reviews").json()
    gen_finds = [f for f in reports[0]["findings"] if f["code"] == "generation"]
    assert len(gen_finds) == 1 and gen_finds[0]["severity"] == "red"
    assert "재생성" in gen_finds[0]["message"]


def test_review_llm_failure_keeps_deterministic_findings(client, app):
    client.post("/api/projects", json={"slug": "rev-llm-fail", "title": "x"})
    _approved_plan(app, 1)

    r = client.post("/api/projects/1/derivatives", json={"kind": "report", "fmts": ["md"]})
    _run_queue(app, FakeLLM([tool_call("write_report_json", correct_report_payload())]))

    client.post("/api/projects/1/reviews")
    # review LLM이 도구 없이 텍스트만 반환 → 내용 검수 실패, 결정론 결과는 보존
    _run_queue(app, FakeLLM([{"content": "도구를 못 찾겠습니다", "tool_calls": []}] * 2),
               profile="review")

    reports = client.get("/api/projects/1/reviews").json()
    assert len(reports) == 1
    rep = reports[0]
    assert rep["llm_ok"] is False
    assert any(f["code"] == "llm-review" for f in rep["findings"])