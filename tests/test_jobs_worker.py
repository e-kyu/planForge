# -*- coding: utf-8 -*-
"""작업 큐 + derive/build 통합 테스트 — fake LLM으로 엔진 통합(승인 게이트·파생·빌드·채번)을 잠근다."""
from __future__ import annotations

from pathlib import Path

from fakes import FakeLLM, correct_report_payload, correct_slides_payload, plan_sample_markdown, tool_call

FIX = Path(__file__).parent / "fixtures"


def _approved_plan(db_session_factory, project_id: int) -> int:
    """승인된 plan 행을 직접 적립한다 (plan 편집 API는 PR-5)."""
    from app.models import Plan, PlanOrigin, PlanStatus

    with db_session_factory() as s:
        plan = Plan(project_id=project_id, version_no=1,
                    markdown=plan_sample_markdown(), docs=["제안서", "개발설계서"],
                    parsed_ok=True, status=PlanStatus.APPROVED, origin=PlanOrigin.EDIT)
        s.add(plan)
        s.commit()
        return plan.id


def _run_queue(app, llm):
    from app.config import get_settings
    from app.db import make_session_factory
    from app.worker import JobContext, claim_next_job, run_job

    ctx = JobContext(
        session_factory=make_session_factory(app.state.settings.database_url),
        settings=get_settings(),
        llm_overrides={"derive": llm},
    )
    s = ctx.session_factory()
    try:
        job = claim_next_job(s)
        if job is not None:
            run_job(ctx, job)
    finally:
        s.close()
    return ctx


def test_derive_build_report_job_end_to_end(client, app, db_env):
    from app.db import make_session_factory

    client.post("/api/projects", json={"slug": "queue-demo", "title": "큐 데모"})
    pid = 1
    plan_id = _approved_plan(make_session_factory(app.state.settings.database_url), pid)

    r = client.post(f"/api/projects/{pid}/derivatives",
                    json={"kind": "report", "fmts": ["md"]})
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]

    llm = FakeLLM([tool_call("write_report_json", correct_report_payload())])
    _run_queue(app, llm)

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "done", job
    assert job["result"]["counts"]["sections"] == 5

    # 파생물 행 — plan 세대 바인딩 (추적성 §5)
    ders = client.get(f"/api/projects/{pid}/derivatives").json()
    assert len(ders) == 1
    assert ders[0]["plan_id"] == plan_id and ders[0]["doc"] == "제안서"

    # 산출물 v01 — 파일 존재 + fs 채번 미러
    outs = client.get(f"/api/projects/{pid}/outputs").json()
    assert len(outs) == 1 and outs[0]["ext"] == "md" and outs[0]["version_no"] == 1
    f = db_env / "queue-demo" / outs[0]["file_path"]
    assert f.is_file()
    assert "11.5시간" in f.read_text(encoding="utf-8")  # 수치 무결성


def test_derive_build_slides_job_creates_pptx(client, app, db_env):
    from app.db import make_session_factory

    client.post("/api/projects", json={"slug": "ppt-demo", "title": "ppt"})
    _approved_plan(make_session_factory(app.state.settings.database_url), 1)
    r = client.post("/api/projects/1/derivatives", json={"kind": "slides"})
    assert r.status_code == 202
    job_id = r.json()["id"]

    llm = FakeLLM([tool_call("write_slides_json", correct_slides_payload())])
    _run_queue(app, llm)

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "done", job
    outs = client.get("/api/projects/1/outputs").json()
    assert len(outs) == 1 and outs[0]["ext"] == "pptx"
    assert (db_env / "ppt-demo" / outs[0]["file_path"]).is_file()
    # SSOT 미러: work/slides.json이 derive 경로에서만 기록됨
    assert (db_env / "ppt-demo" / "work" / "slides.json").is_file()


def test_unapproved_plan_blocks_derive(client, app):
    client.post("/api/projects", json={"slug": "no-approve", "title": "x"})
    r = client.post("/api/projects/1/derivatives", json={"kind": "report"})
    assert r.status_code == 409
    assert "승인" in r.json()["detail"]


def test_llm_failure_classified_as_llm_error(client, app, db_env):
    from app.db import make_session_factory

    client.post("/api/projects", json={"slug": "fail-demo", "title": "x"})
    _approved_plan(make_session_factory(app.state.settings.database_url), 1)
    r = client.post("/api/projects/1/derivatives",
                    json={"kind": "report", "fmts": ["md"]})
    job_id = r.json()["id"]

    bad = correct_report_payload()
    bad["sections"][3]["blocks"][0]["rows"][0][1] = "주 99시간 수기 작성"  # 수치 왜곡 지속
    llm = FakeLLM([tool_call("write_report_json", bad)] * 3)
    _run_queue(app, llm)

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert job["error_class"] == "llm"
    # 불완전 산출물이 output에 남지 않는다 (§5 원자성)
    assert not list((db_env / "fail-demo" / "output").glob("*.md"))


def test_claim_returns_none_on_empty_queue(app):
    from app.db import make_session_factory
    from app.worker import claim_next_job

    s = make_session_factory(app.state.settings.database_url)()
    try:
        assert claim_next_job(s) is None
    finally:
        s.close()


def test_report_build_defaults_to_three_formats(client, app, db_env):
    from app.db import make_session_factory

    client.post("/api/projects", json={"slug": "fmt-demo", "title": "x"})
    _approved_plan(make_session_factory(app.state.settings.database_url), 1)
    r = client.post("/api/projects/1/derivatives", json={"kind": "report"})
    job_id = r.json()["id"]

    llm = FakeLLM([tool_call("write_report_json", correct_report_payload())])
    _run_queue(app, llm)

    outs = client.get("/api/projects/1/outputs").json()
    assert {o["ext"] for o in outs} == {"md", "html", "docx"}
    # 확장자별 독립 시퀀스 — 모두 v01 (원칙 5)
    assert all(o["version_no"] == 1 for o in outs)