# -*- coding: utf-8 -*-
"""인터뷰 에이전트 e2e 테스트 — 가짜 스트리밍 LLM으로 SSE 턴 흐름을 잠근다.

흐름: kick(가설+질문) → answers → save_facts 게이트 → 승인 → key messages 승인 →
write_plan → plan 승인 → derive/build e2e (FR-2 수용 시나리오 1).
"""
from __future__ import annotations

import json

import pytest

from fakes import (
    FakeLLM,
    FakeStreamLLM,
    correct_report_payload,
    plan_sample_markdown,
    tool_call,
)


def _sse_events(client, url, payload=None):
    """POST + SSE 스트림 소비 → [(event_name, payload), ...]."""
    with client.stream("POST", url, json=payload or {}) as r:
        assert r.status_code == 200, r.read()
        events = []
        name = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: ") and name:
                events.append((name, json.loads(line[6:])))
                name = None
        return events


@pytest.fixture()
def fake_llm():
    return FakeStreamLLM([
        # 턴1 kick: 가설 텍스트 + 라운드 1 질문
        ("가설 초안: 목적은 보고 업무 자동화 도입 설득이다.", [
            ("update_checklist", {"items": [{"id": "c1", "area": "공통", "text": "목적 확정", "done": True}]}),
            ("ask_questions", {"round_summary": "뼈대 확인",
                               "questions": [{"text": "청중은 누구인가?", "allow_free": True}]}),
        ]),
        # 턴2 answers: 팩트 확인 게이트 제시
        ("", [
            ("save_facts", {"facts": [
                {"content": "보고 작성이 주 10시간 수기 작성이다", "source": "인터뷰"},
                {"content": "부서별 양식 상이로 취합이 수작업이다", "source": "인터뷰"},
                {"content": "4분기 시범 도입을 목표로 한다", "source": "인터뷰"},
            ]}),
        ]),
        # 턴3 팩트 승인 후: 핵심 메시지 승인 카드
        ("", [
            ("confirm_key_messages", {"messages": [
                "주 11.5시간 절감", "표준 파이프라인", "시범 도입 후 확장"]}),
        ]),
        # 턴4 핵심 메시지 승인 후: plan 작성
        ("", [
            ("write_plan", {"markdown": plan_sample_markdown()}),
        ]),
    ])


@pytest.fixture()
def sapp(db_env, test_engine, fake_llm):
    from app.main import create_app

    return create_app(start_worker=False, llm_overrides={"interview": fake_llm})


@pytest.fixture()
def sclient(sapp):
    from fastapi.testclient import TestClient

    with TestClient(sapp) as c:
        yield c


def _setup(sclient) -> int:
    sclient.post("/api/projects", json={"slug": "interview-e2e", "title": "인터뷰 e2e"})
    r = sclient.post("/api/projects/1/interview/sessions", json={})
    assert r.status_code == 201
    return r.json()["id"]


def test_interview_full_flow_to_plan_approval(sclient, sapp, fake_llm, db_env):
    sid = _setup(sclient)

    # kick — 가설 선제시 + 질문 카드 (FR-2.2/2.3)
    events = _sse_events(sclient, f"/api/interview/sessions/{sid}/kick")
    names = [n for n, _ in events]
    assert "questions" in names and "state" in names and "done" in names
    assert names[0] == "state"  # 턴 시작 시 현재 상태 먼저 전송
    s = sclient.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "awaiting_answers" and s["round_no"] == 1
    assert s["pending_questions"][0]["text"] == "청중은 누구인가?"

    # 시스템 프롬프트가 주입됐는지 — 첫 LLM 호출의 첫 메시지
    first_call = fake_llm.calls[0]
    assert first_call[0]["role"] == "system"
    assert "인터뷰 에이전트" in first_call[0]["content"]

    # answers — 라운드 답변 (FR-2.3)
    events = _sse_events(sclient, f"/api/interview/sessions/{sid}/answers",
                         {"answers": [{"index": 0, "free_text": "경영진 — 도입 승인 판단"}]})
    assert "facts" in [n for n, _ in events]
    s = sclient.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "fact_gate"
    assert len(s["pending_facts"]) == 3

    # 팩트 승인 전에는 팩트 저장소에 없다 (FR-2.4)
    assert sclient.get("/api/projects/1/facts").json() == []

    # facts confirm — 승인 시에만 적립 (FR-2.4) + 다음 턴 진행
    events = _sse_events(sclient, f"/api/interview/sessions/{sid}/facts/confirm",
                         {"approve": True})
    assert "key_messages" in [n for n, _ in events]
    facts = sclient.get("/api/projects/1/facts").json()
    assert len(facts) == 3
    assert facts[0]["content"] == "보고 작성이 주 10시간 수기 작성이다"
    # interview-log 미러 (원칙 4)
    log = db_env / "interview-e2e" / "docs" / "interview-log.md"
    assert "주 10시간 수기 작성" in log.read_text(encoding="utf-8")
    s = sclient.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "key_message_gate"

    # key messages 승인 (FR-2.6)
    events = _sse_events(sclient, f"/api/interview/sessions/{sid}/key-messages",
                         {"approve": True})
    assert "plan_draft" in [n for n, _ in events]
    s = sclient.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "plan_review"
    assert s["key_messages_approved"] is True

    # plan 승인 게이트 (FR-2.9)
    plan_id = events[[n for n, _ in events].index("plan_draft")][1]["plan_id"]
    r = sclient.post(f"/api/plans/{plan_id}/approve")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    s = sclient.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "approved" and s["status"] == "done"
    # plan.md 미러 — SSOT(DB)의 파일 형태
    assert (db_env / "interview-e2e" / "plan.md").read_text(encoding="utf-8") == plan_sample_markdown()


def test_gate_phase_mismatches_are_409(sclient, fake_llm):
    sid = _setup(sclient)
    # facts 게이트가 열리지 않은 상태에서 confirm → 409
    r = sclient.post(f"/api/interview/sessions/{sid}/facts/confirm", json={"approve": True})
    assert r.status_code == 409
    # key messages 게이트 → 409
    r = sclient.post(f"/api/interview/sessions/{sid}/key-messages", json={"approve": True})
    assert r.status_code == 409
    # 질문 대기 전 answers → 409
    r = sclient.post(f"/api/interview/sessions/{sid}/answers",
                     json={"answers": [{"index": 0, "free_text": "x"}]})
    assert r.status_code == 409


def test_plan_validation_error_loops_back(sclient, fake_llm):
    """write_plan 검증 실패 → ERROR 피드백으로 재호출 유도 → 재시도 성공."""
    bad = "# 기획\n\n## 메타\n- 목적: x\n\n## 핵심 메시지 (3개)\n1. a\n\n## 슬라이드 목록\n"
    fake_llm.turns = [
        ("", [("ask_questions", {"questions": [{"text": "q", "allow_free": True}]})]),
        ("", [("save_facts", {"facts": [{"content": "f1", "source": "인터뷰"}]})]),
        ("", [("confirm_key_messages", {"messages": ["a", "b", "c"]})]),
        ("", [("write_plan", {"markdown": bad})]),   # 검증 실패 (핵심 메시지 1개)
        ("", [("write_plan", {"markdown": plan_sample_markdown()})]),
    ]
    sid = _setup(sclient)
    _sse_events(sclient, f"/api/interview/sessions/{sid}/kick")
    _sse_events(sclient, f"/api/interview/sessions/{sid}/answers",
                {"answers": [{"index": 0, "free_text": "답"}]})
    _sse_events(sclient, f"/api/interview/sessions/{sid}/facts/confirm", {"approve": True})
    events = _sse_events(sclient, f"/api/interview/sessions/{sid}/key-messages",
                         {"approve": True})
    assert "plan_draft" in [n for n, _ in events]


def test_interview_to_build_end_to_end(sclient, sapp, fake_llm, db_env):
    """수용 기준 1 — API로 인터뷰→빌드 e2e (report md 산출물)."""
    sid = _setup(sclient)
    _sse_events(sclient, f"/api/interview/sessions/{sid}/kick")
    _sse_events(sclient, f"/api/interview/sessions/{sid}/answers",
                {"answers": [{"index": 0, "free_text": "경영진"}]})
    _sse_events(sclient, f"/api/interview/sessions/{sid}/facts/confirm", {"approve": True})
    events = _sse_events(sclient, f"/api/interview/sessions/{sid}/key-messages",
                         {"approve": True})
    plan_id = events[[n for n, _ in events].index("plan_draft")][1]["plan_id"]
    assert sclient.post(f"/api/plans/{plan_id}/approve").status_code == 200

    r = sclient.post("/api/projects/1/derivatives", json={"kind": "report", "fmts": ["md"]})
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]

    # 단일 워커 직렬화는 run_job 직접 호출로 결정론 검증 (worker 루프는 비활성)
    from app.config import get_settings
    from app.db import make_session_factory
    from app.worker import JobContext, claim_next_job, run_job

    derive_llm = FakeLLM([tool_call("write_report_json", correct_report_payload())])
    ctx = JobContext(
        session_factory=make_session_factory(sapp.state.settings.database_url),
        settings=get_settings(),
        llm_overrides={"derive": derive_llm},
    )
    s = ctx.session_factory()
    try:
        job = claim_next_job(s)
        assert job is not None
        run_job(ctx, job)
    finally:
        s.close()

    job = sclient.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "done", job
    outs = sclient.get("/api/projects/1/outputs").json()
    assert len(outs) == 1 and outs[0]["version_no"] == 1
    f = db_env / "interview-e2e" / outs[0]["file_path"]
    assert f.is_file()
    assert "11.5시간" in f.read_text(encoding="utf-8")  # 수치 무결성