# -*- coding: utf-8 -*-
"""작업 큐 + derive/build 통합 테스트 — fake LLM으로 엔진 통합(승인 게이트·파생·빌드·채번)을 잠근다."""
from __future__ import annotations

from fakes import FakeLLM, correct_report_payload, correct_slides_payload, tool_call
from _helpers import insert_plan, make_project, make_session, run_queue, session_factory


def test_derive_build_report_job_end_to_end(client, app, db_env):
    make_project(client, "queue-demo", "큐 데모")
    plan_id = insert_plan(app, 1, docs=("제안서", "개발설계서"))

    r = client.post(f"/api/projects/1/derivatives",
                    json={"kind": "report", "fmts": ["md"]})
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]

    llm = FakeLLM([tool_call("write_report_json", correct_report_payload())])
    run_queue(app, llm)

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "done", job
    assert job["result"]["counts"]["sections"] == 5
    # 진행 상태 — 마지막 기록 단계가 남는다 (표시는 running일 때만, 완료는 status가 담당)
    assert job["progress"]["step"] == "build"
    assert "MD" in job["progress"]["detail"]  # fmt별 진행 상세 — 빌드 루프가 기록
    assert job["started_at"] is not None  # 경과시간 계약 — JobOut 노출 확인

    # 파생물 행 — plan 세대 바인딩 (추적성 §5)
    ders = client.get("/api/projects/1/derivatives").json()
    assert len(ders) == 1
    assert ders[0]["plan_id"] == plan_id and ders[0]["doc"] == "제안서"

    # 산출물 v01 — 파일 존재 + fs 채번 미러
    outs = client.get("/api/projects/1/outputs").json()
    assert len(outs) == 1 and outs[0]["ext"] == "md" and outs[0]["version_no"] == 1
    f = db_env / "queue-demo" / outs[0]["file_path"]
    assert f.is_file()
    assert "11.5시간" in f.read_text(encoding="utf-8")  # 수치 무결성


def test_derive_build_slides_job_creates_pptx(client, app, db_env):
    make_project(client, "ppt-demo", "ppt")
    insert_plan(app, 1, docs=("제안서", "개발설계서"))
    r = client.post("/api/projects/1/derivatives", json={"kind": "slides"})
    assert r.status_code == 202
    job_id = r.json()["id"]

    llm = FakeLLM([tool_call("write_slides_json", correct_slides_payload())])
    run_queue(app, llm)

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "done", job
    outs = client.get("/api/projects/1/outputs").json()
    assert len(outs) == 1 and outs[0]["ext"] == "pptx"
    assert (db_env / "ppt-demo" / outs[0]["file_path"]).is_file()
    # SSOT 미러: work/slides.json이 derive 경로에서만 기록됨
    assert (db_env / "ppt-demo" / "work" / "slides.json").is_file()


def test_unapproved_plan_blocks_derive(client, app):
    make_project(client, "no-approve")
    r = client.post("/api/projects/1/derivatives", json={"kind": "report"})
    assert r.status_code == 409
    assert "승인" in r.json()["detail"]


def test_numeric_distortion_job_done_with_findings(client, app, db_env):
    """수치 왜곡은 생성 실패가 아니다 (결정 17 — 판정 권위는 검수 단계).

    왜곡 지속 LLM 변환 1회 → job done, 측정값 findings가 job.result에 영속 기록되고
    위반 수치가 실제 산출물 md에 남는다."""
    make_project(client, "fail-demo")
    insert_plan(app, 1, docs=("제안서", "개발설계서"))
    r = client.post("/api/projects/1/derivatives",
                    json={"kind": "report", "fmts": ["md"]})
    job_id = r.json()["id"]

    bad = correct_report_payload()
    bad["sections"][3]["blocks"][0]["rows"][0][1] = "주 99시간 수기 작성"  # plan에 없는 수치 — 창작 red
    llm = FakeLLM([tool_call("write_report_json", bad)])
    run_queue(app, llm)

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "done", job
    assert job["error_class"] is None
    assert len(llm.calls) == 1  # 수치 재시도 없음 — 1회 변환으로 통과
    reds = [f for f in job["result"]["findings"] if f["severity"] == "red"]
    assert reds and any("99" in f["message"] for f in reds)
    # 게이트 폐지 — 위반 수치가 실린 산출물이 실제로 채번돼 존재한다 (원칙 5 추적성)
    outs = client.get("/api/projects/1/outputs").json()
    assert outs and outs[0]["version_no"] == 1
    md = db_env / "fail-demo" / outs[0]["file_path"]
    assert md.is_file() and "99" in md.read_text(encoding="utf-8")


def test_llm_schema_failure_classified_as_schema_error(client, app, db_env):
    """스키마 위반 지속 소진 — error_class SCHEMA, 오류문에 builder 진단 실림 (결정 16)."""
    make_project(client, "schema-fail")
    insert_plan(app, 1, docs=("제안서", "개발설계서"))
    r = client.post("/api/projects/1/derivatives",
                    json={"kind": "report", "fmts": ["md"]})
    job_id = r.json()["id"]

    bad = correct_report_payload()
    del bad["sections"][0]["title"]  # 필수 키 누락 — build_doc.validate 위반
    llm = FakeLLM([tool_call("write_report_json", bad)] * 3)
    run_queue(app, llm)

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert job["error_class"] == "schema"
    assert "스키마 검증 실패" in job["error"]
    assert "필수 키 누락" in job["error"]     # builder가 낸 실제 진단
    assert "수치 무결성" not in job["error"]  # 거짓 라벨링 회귀 방지
    # 불완전 산출물이 output에 남지 않는다 (§5 원자성)
    assert not list((db_env / "schema-fail" / "output").glob("*.md"))


def test_reds_auto_enqueue_review(client, app):
    """red 잔여 derive done → 검수 잡이 같은 커밋에 자동 큐잉되고, 그 잡이 같은 red를
    🔴 리포트로 판정한다 (수용 기준 3 e2e — 결정 17: 판정 권위는 검수 단계)."""
    make_project(client, "auto-review")
    plan_id = insert_plan(app, 1, docs=("제안서", "개발설계서"))
    r = client.post("/api/projects/1/derivatives",
                    json={"kind": "report", "fmts": ["md"]})
    derive_job_id = r.json()["id"]

    bad = correct_report_payload()
    bad["sections"][3]["blocks"][0]["rows"][0][1] = "주 99시간 수기 작성"
    run_queue(app, FakeLLM([tool_call("write_report_json", bad)]))
    assert client.get(f"/api/jobs/{derive_job_id}").json()["status"] == "done"

    jobs = client.get("/api/projects/1/jobs").json()
    revs = [j for j in jobs if j["type"] == "review"]
    assert len(revs) == 1
    rev = revs[0]
    assert rev["status"] == "queued"
    assert rev["payload"]["plan_id"] == plan_id
    assert rev["payload"]["auto"] is True  # 자동 큐잉 표식

    # 자동 큐잉된 검수 잡을 실행 — 도구 없는 review LLM(결정론 결과만 반영)으로
    run_queue(app, FakeLLM([{"content": "도구 없는 텍스트", "tool_calls": []}] * 2),
              profile="review")

    rev2 = [j for j in client.get("/api/projects/1/jobs").json() if j["type"] == "review"][0]
    assert rev2["status"] == "done"
    reports = client.get("/api/projects/1/reviews").json()
    assert len(reports) == 1
    num = [f for f in reports[0]["findings"] if f["code"] == "numeric-extra"]
    assert num and num[0]["severity"] == "red" and "99" in num[0]["message"]
    assert reports[0]["red_count"] >= 1


def test_clean_derive_no_auto_review(client, app):
    """클린 생성은 검수를 자동 큐잉하지 않는다 (결정 17 — 위반 있을 때만 자동)."""
    make_project(client, "clean-demo")
    insert_plan(app, 1, docs=("제안서", "개발설계서"))
    r = client.post("/api/projects/1/derivatives", json={"kind": "slides"})
    run_queue(app, FakeLLM([tool_call("write_slides_json", correct_slides_payload())]))

    job = client.get(f"/api/jobs/{r.json()['id']}").json()
    assert job["status"] == "done", job
    assert job["result"].get("findings") is None  # 클린 대조 — 측정값 없음
    assert [j["type"] for j in client.get("/api/projects/1/jobs").json()] == ["derive_build"]


def test_enqueue_auto_review_dedupe(client, app):
    """같은 plan 세대의 활성(queued/running) 검수 잡이 이미 있으면 중복 큐잉하지 않는다."""
    from app.modules.jobs.facade import JobType, enqueue
    from app.modules.review.facade import enqueue_auto_review

    make_project(client, "dedupe-demo")
    with make_session(app) as s:
        enqueue(s, 1, JobType.REVIEW, {"plan_id": 7})
        s.commit()
    with make_session(app) as s:
        assert enqueue_auto_review(s, 1, 7) is None
    with make_session(app) as s:
        job = enqueue_auto_review(s, 1, 8)
        s.commit()
        assert job is not None  # 다른 plan 세대는 큐잉된다


def test_build_failure_leaves_no_derivative_or_output(client, app, db_env, monkeypatch):
    """빌더 실패 → 고아 Derivative·산출물 파일 0건 (진행 불변식 회귀 — 도메인 행은
    atomic_build 이후에만 생성: report_progress 커밋이 조기 행 확정을 만들지 않는다)."""
    make_project(client, "build-fail")
    insert_plan(app, 1, docs=("제안서", "개발설계서"))
    r = client.post("/api/projects/1/derivatives",
                    json={"kind": "report", "fmts": ["md"]})
    job_id = r.json()["id"]

    import planforge.builders.build_doc as build_doc_mod

    def raiser(json_path: str, fmt: str, out_dir: str) -> None:
        raise RuntimeError("builder exploded")

    monkeypatch.setattr(build_doc_mod, "build", raiser)

    llm = FakeLLM([tool_call("write_report_json", correct_report_payload())])
    run_queue(app, llm)

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "failed", job
    # 진행 상태 — 빌드 단계 기록까지 남는다 (마지막 진행 기록)
    assert job["progress"]["step"] == "build"
    # 고아 없음 — 파생물행·빌드행·output 파일 모두 없어야 한다 (§5 원자성)
    assert client.get("/api/projects/1/derivatives").json() == []
    assert client.get("/api/projects/1/outputs").json() == []
    assert not list((db_env / "build-fail" / "output").glob("*"))


def test_claim_returns_none_on_empty_queue(app):
    from app.modules.jobs.application.worker import claim_next_job

    with make_session(app) as s:
        assert claim_next_job(s) is None


def test_report_build_defaults_to_three_formats(client, app, db_env):
    make_project(client, "fmt-demo")
    insert_plan(app, 1, docs=("제안서", "개발설계서"))
    r = client.post("/api/projects/1/derivatives", json={"kind": "report"})
    job_id = r.json()["id"]

    llm = FakeLLM([tool_call("write_report_json", correct_report_payload())])
    run_queue(app, llm)

    outs = client.get("/api/projects/1/outputs").json()
    assert {o["ext"] for o in outs} == {"md", "html", "docx"}
    # 확장자별 독립 시퀀스 — 모두 v01 (원칙 5)
    assert all(o["version_no"] == 1 for o in outs)


def test_requeue_stale_running_resets_progress(client, app):
    """재큐잉 시 running 잔재의 progress·started_at도 초기화 — stale 진행 노출 방지."""
    from app.modules.jobs.application.worker import claim_next_job, requeue_stale_running
    from app.modules.jobs.facade import JobStatus, JobType, enqueue, report_progress
    from app.modules.jobs.infrastructure.models import Job

    make_project(client, "requeue-demo")
    with make_session(app) as s:
        job = enqueue(s, 1, JobType.DERIVE_BUILD, {"kind": "slides"})
        s.commit()
        job_id = job.id

    with make_session(app) as s:  # claim → running 시점 + 진행 기록
        job = claim_next_job(s)
        assert job is not None and job.id == job_id
        report_progress(s, job, "llm", attempt=1, max_attempts=3)

    assert requeue_stale_running(session_factory(app)) == 1
    with make_session(app) as s:
        job = s.get(Job, job_id)
        assert job.status == JobStatus.QUEUED
        assert job.started_at is None and job.progress is None