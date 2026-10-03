# -*- coding: utf-8 -*-
"""인터뷰 에이전트 e2e 테스트 — 가짜 스트리밍 LLM으로 SSE 턴 흐름을 잠근다.

흐름: kick(가설+질문) → answers → save_facts 게이트 → 승인 → key messages 승인 →
write_plan → plan 승인 → derive/build e2e (FR-2 수용 시나리오 1).
"""
from __future__ import annotations

import json

import pytest

from app.agents.tools import MAX_SUGGESTIONS
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
    assert names[0] == "progress"  # 턴 시작 즉시 컨텍스트 조립 진행 알림(progress) 먼저 전송
    assert events[0][1] == {"step": "context"}
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


def test_kick_emits_progress_and_not_persisted(sclient, fake_llm):
    """progress 이벤트: 첫 토큰 전 구간 진행을 알리며, emit-only라 이력에 영속되지 않는다."""
    sid = _setup(sclient)
    events = _sse_events(sclient, f"/api/interview/sessions/{sid}/kick")
    names = [n for n, _ in events]
    assert names[0] == "progress" and events[0][1] == {"step": "context"}
    steps = [p["step"] for n, p in events if n == "progress"]
    assert "llm" in steps and "tool" in steps
    # 미영속 — GET /messages 리플레이에 progress가 없고, 빈 content의 text 행도 없다
    msgs = sclient.get(f"/api/interview/sessions/{sid}/messages").json()
    assert all(m["kind"] != "progress" for m in msgs)
    assert all(m["content"] for m in msgs if m["role"] == "assistant" and m["kind"] == "text")


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
    from app.shared.config import get_settings
    from app.shared.db import make_session_factory
    from app.modules.jobs.application.worker import JobContext, claim_next_job, run_job

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


# ------------------------------------------------------- 개발설계서 설계 결정 설문 (FR-2 보강)

DESIGN_PLAN_MARKDOWN = """# 개발설계 (보고 파이프라인 시스템)

## 메타
- 산출 문서: 개발설계서
- 목적: 설계 결정(아키텍처·기술 스택·규약·비목표)의 확정
- 청중: 개발팀
- 예상 분량: 5장

## 핵심 메시지 (3개)
1. 레이어드 모놀리식으로 운영을 단순하게 유지한다
2. FastAPI + SQLAlchemy 2.x 스택으로 API 계약을 코드로 잠근다
3. 인증·클라우드 배포는 비목표로 고정해 범위를 지킨다

## 슬라이드 목록

### 1. [유형: 표지] 보고 파이프라인 시스템 개발설계서
- 핵심문장: 설계 결정의 확정으로 구축 착수 기준을 제시한다
- 근거/출처: interview-log [2026-09-22] 설계 결정 설문 (샘플)

### 2. [유형: 목차] 목차
- 핵심문장: 01 요구사항 현황 / 02 시스템 구성도 / 03 기술 스택 결정 / 04 API 규약 / 05 제약·비목표 / 06 확인 및 합의 사항

### 3. [유형: 2단] 요구사항 현황
- 좌 (현황):
  - 보고 작성 | 주 10시간 수기 작성
- 우 (요구사항):
  - 자동화 | 보고 생성·취합 파이프라인 자동화
- 근거/출처: interview-log [2026-09-22] 해결 문제 (샘플)

### 4. [유형: 구성] 시스템 구성도
- 구성:
  - 사용자 계층 | 웹 UI
  - 서비스 계층 | REST API, 작업 큐 워커
  - 데이터 계층 | SQLite (WAL)
- 근거/출처: interview-log [2026-09-22] 아키텍처 확정 (샘플)

### 5. [유형: 표] 기술 스택 결정
- 표: [항목 | 선택 | 이유 | 상태]
  - 언어 | Python 3.12 | 팀 경험 | 확정
  - 웹 프레임워크 | FastAPI | 비동기 지원·OpenAPI 자동화 | 확정
  - 캐시 | Redis | 대안 검토 필요 | (미확정)
- 근거/출처: interview-log [2026-09-22] 기술 스택 결정 (샘플)

### 6. [유형: 표] API 규약
- 표: [항목 | 방식 | 규약 | 상태]
  - 계약 방식 | OpenAPI 스키마 우선 | 타입 자동 생성 | 확정
  - 오류 응답 | 통일 | 표준 오류 JSON | 확정
- 근거/출처: interview-log [2026-09-22] API 규약 확정 (샘플)

### 7. [유형: 2단] 제약·비목표
- 좌 (제약):
  - 단일 워커 | 빌드 작업은 DB 작업 큐로 직렬화 (병렬 금지)
- 우 (비목표):
  - 인증 | 사내망 신뢰 전제로 생략
- 근거/출처: interview-log [2026-09-22] 제약·비목표 확정 (샘플)

### 8. [유형: 마무리] 확인 및 합의 사항
- 핵심문장: 캐시 도구 선정이 남은 (미확정) 항목 — 다음 스프린트에서 확정
- 근거/출처: interview-log [2026-09-22] 설계 결정 확인 계획 (샘플)
"""


@pytest.fixture()
def design_llm():
    return FakeStreamLLM([
        # 턴1 kick: 가설(산출 문서 목록 첫 확정) + 설계 결정 설문 라운드 1
        ("가설 초안: 산출 문서는 개발설계서 단독 — 설계 결정 설문을 진행한다.", [
            ("update_checklist", {"items": [
                {"id": "d1", "area": "개발설계서", "text": "아키텍처 스타일·시스템 구성 확정",
                 "done": False},
                {"id": "d2", "area": "개발설계서", "text": "기술 스택·모듈/패키지 구조 확정",
                 "done": False},
            ]}),
            ("ask_questions", {
                "round_summary": "라운드 1 목표: 아키텍처 스타일·기술 스택 확정",
                "questions": [
                    {"text": "시스템 구조는 어떻게 잡나요?", "options": [
                        {"label": "레이어드 모놀리식",
                         "description": "계층 분리·단일 배포 — 운영이 단순"},
                        {"label": "마이크로서비스",
                         "description": "도메인별 독립 배포 — 운영이 복잡"}]},
                    {"text": "언어·프레임워크·버전과 패키지 구조는?", "allow_free": True},
                ]}),
        ]),
        # 턴2 answers: 설계 결정 팩트 확인 게이트 (주제당 1개 팩트 — 결정+이유+대안)
        ("", [
            ("save_facts", {"facts": [
                {"content": "아키텍처: 레이어드 모놀리식 3계층 — 단일 배포로 운영 단순 "
                            "(대안 마이크로서비스는 운영 복잡도로 제외)", "source": "인터뷰 라운드 1"},
                {"content": "기술 스택: Python 3.12 + FastAPI + SQLAlchemy 2.x — 대안 Django는 "
                            "전환 비용으로 제외", "source": "인터뷰 라운드 1"},
                {"content": "API 규약: OpenAPI 스키마 우선, 오류 응답 통일", "source": "인터뷰 라운드 1"},
                {"content": "비목표: 인증은 이번 범위 아님 — SSO 연동은 (미확정)", "source": "인터뷰 라운드 1"},
            ]}),
        ]),
        # 턴3 팩트 승인 후: 핵심 메시지 승인 카드
        ("", [
            ("confirm_key_messages", {"messages": [
                "레이어드 모놀리식으로 운영을 단순하게 유지한다",
                "FastAPI + SQLAlchemy 2.x 스택으로 API 계약을 코드로 잠근다",
                "인증·클라우드 배포는 비목표로 고정한다"]}),
        ]),
        # 턴4 핵심 메시지 승인 후: plan 작성 (단일 문서 — 태그 없음 규칙)
        ("", [
            ("write_plan", {"markdown": DESIGN_PLAN_MARKDOWN}),
        ]),
    ])


@pytest.fixture()
def dapp(db_env, test_engine, design_llm):
    from app.main import create_app

    return create_app(start_worker=False, llm_overrides={"interview": design_llm})


@pytest.fixture()
def dclient(dapp):
    from fastapi.testclient import TestClient

    with TestClient(dapp) as c:
        yield c


def test_interview_design_arc_full_flow_to_plan_approval(dclient, design_llm, db_env):
    """개발설계서 설계 결정 설문 — 가설(문서 목록 첫 확정) → 설계 질문 → 설계 결정 팩트
    → 핵심 메시지 → plan(결정표·구성·비목표) → 승인."""
    dclient.post("/api/projects", json={"slug": "design-e2e", "title": "설계 아크 e2e"})
    r = dclient.post("/api/projects/1/interview/sessions", json={})
    assert r.status_code == 201
    sid = r.json()["id"]

    # kick — 가설 선제시 + 설계 질문 카드
    events = _sse_events(dclient, f"/api/interview/sessions/{sid}/kick")
    assert "questions" in [n for n, _ in events]
    s = dclient.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "awaiting_answers" and s["round_no"] == 1
    assert s["pending_round_summary"] == "라운드 1 목표: 아키텍처 스타일·기술 스택 확정"
    assert any(i["area"] == "개발설계서" for i in s["checklist"])
    # 보강된 프롬프트(설계 결정 설문)가 시스템 프롬프트로 주입됐는지
    first_call = design_llm.calls[0]
    assert first_call[0]["role"] == "system"
    assert "인터뷰 에이전트" in first_call[0]["content"]
    assert "설계 결정 설문" in first_call[0]["content"]

    # answers → 설계 결정 팩트 게이트
    _sse_events(dclient, f"/api/interview/sessions/{sid}/answers",
                {"answers": [{"index": 0, "option": 0},
                             {"index": 1, "free_text": "Python 3.12 + FastAPI"}]})
    s = dclient.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "fact_gate" and len(s["pending_facts"]) == 4

    # 팩트 승인 — 설계 결정이 팩트 저장소에 적립된다 (원칙 4)
    _sse_events(dclient, f"/api/interview/sessions/{sid}/facts/confirm", {"approve": True})
    facts = dclient.get("/api/projects/1/facts").json()
    assert len(facts) == 4
    contents = " ".join(f["content"] for f in facts)
    assert "레이어드 모놀리식" in contents
    assert "대안 Django는 전환 비용으로 제외" in contents
    assert "(미확정)" in contents
    log = db_env / "design-e2e" / "docs" / "interview-log.md"
    assert "레이어드 모놀리식" in log.read_text(encoding="utf-8")
    s = dclient.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "key_message_gate"

    # 핵심 메시지 승인 → plan 작성
    events = _sse_events(dclient, f"/api/interview/sessions/{sid}/key-messages",
                         {"approve": True})
    assert "plan_draft" in [n for n, _ in events]
    draft = events[[n for n, _ in events].index("plan_draft")][1]
    assert draft["docs"] == ["개발설계서"]
    s = dclient.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "plan_review" and s["key_messages_approved"] is True

    # plan 승인 게이트
    r = dclient.post(f"/api/plans/{draft['plan_id']}/approve")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    s = dclient.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "approved" and s["status"] == "done"

    # plan.md 미러 — 결정표·(미확정)·구성이 원문 그대로 보존된다
    mirror = (db_env / "design-e2e" / "plan.md").read_text(encoding="utf-8")
    assert mirror == DESIGN_PLAN_MARKDOWN
    from planforge.plan import filter_slides, parse_plan_text, validate_skeleton

    plan = parse_plan_text(mirror)
    assert plan.docs == ["개발설계서"]
    table = next(s for s in plan.slides if s.type == "table")
    assert table.table.headers == ["항목", "선택", "이유", "상태"]
    assert any(row[-1] == "(미확정)" for row in table.table.rows)  # (미확정) 상태 셀 원문 보존
    arch = next(s for s in plan.slides if s.type == "arch")
    assert len(arch.arch) == 3
    validate_skeleton(filter_slides(plan.slides, "개발설계서"))  # 골격 검증 (원칙 8)


# ---------------------------------------------------------------------------
# 질문 선택지 계약 강제 — 누락 시 ERROR 피드백 → 재호출 (turn_graph route_after_blocking)


@pytest.fixture()
def retry_llm():
    return FakeStreamLLM([
        # 턴1 1호출 — 선택지가 누락된 ask_questions (validate_tool_args 실패 → ERROR)
        ("", [("ask_questions", {"round_summary": "뼈대 확인",
                                 "questions": [{"text": "청중은 누구인가?"}]})]),
        # 턴1 2호출 — ERROR 피드백을 받아 options를 채워 재호출
        ("", [("ask_questions", {"round_summary": "뼈대 확인",
                                 "questions": [{"text": "청중은 누구인가?", "options": [
                                     {"label": "경영진", "description": "도입 승인 판단"},
                                     {"label": "실무팀", "description": "현업 작성자"}]}]})]),
    ])


@pytest.fixture()
def rapp(db_env, test_engine, retry_llm):
    from app.main import create_app

    return create_app(start_worker=False, llm_overrides={"interview": retry_llm})


@pytest.fixture()
def rclient(rapp):
    from fastapi.testclient import TestClient

    with TestClient(rapp) as c:
        yield c


def test_ask_questions_options_contract_triggers_retry(rclient, retry_llm):
    sid = _setup(rclient)

    events = _sse_events(rclient, f"/api/interview/sessions/{sid}/kick")
    names = [n for n, _ in events]
    assert "questions" in names and "done" in names
    assert len(retry_llm.calls) == 2  # 검증 실패 → ERROR 피드백 → 같은 턴 내 재호출 1회
    tool_feedback = [m["content"] for m in retry_llm.calls[1] if m["role"] == "tool"]
    assert len(tool_feedback) == 1 and tool_feedback[0].startswith("ERROR:")
    assert "선택지" in tool_feedback[0]

    s = rclient.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "awaiting_answers" and s["round_no"] == 1
    q = s["pending_questions"][0]
    assert q["options"][0]["label"] == "경영진"


# ---------------------------------------------------------------------------
# 본문 서술형 선택지 계약 — 선택지는 options 배열로만 전달한다 (본문 "예:" 나열 거부)


@pytest.fixture()
def prose_llm():
    return FakeStreamLLM([
        # 턴1 1호출 — 선택지를 본문에 나열한 ask_questions (prose 탐지 → ERROR)
        ("", [("ask_questions", {"round_summary": "뼈대 확인",
                                 "questions": [{"text": "시스템 구조는 어떻게 잡나요?\n"
                                                "예:\n- 레이어드 모놀리식\n- 마이크로서비스",
                                                "allow_free": True}]})]),
        # 턴1 2호출 — ERROR 피드백을 받아 선택지를 options 배열로 옮겨 재호출
        ("", [("ask_questions", {"round_summary": "뼈대 확인",
                                 "questions": [{"text": "시스템 구조는 어떻게 잡나요?",
                                                "options": [
                                                    {"label": "레이어드 모놀리식",
                                                     "description": "계층 분리·단일 배포"},
                                                    {"label": "마이크로서비스",
                                                     "description": "도메인별 독립 배포"}]}]})]),
    ])


@pytest.fixture()
def prose_app(db_env, test_engine, prose_llm):
    from app.main import create_app

    return create_app(start_worker=False, llm_overrides={"interview": prose_llm})


@pytest.fixture()
def prose_client(prose_app):
    from fastapi.testclient import TestClient

    with TestClient(prose_app) as c:
        yield c


def test_ask_questions_prose_options_triggers_retry(prose_client, prose_llm):
    sid = _setup(prose_client)

    events = _sse_events(prose_client, f"/api/interview/sessions/{sid}/kick")
    assert "questions" in [n for n, _ in events]
    assert len(prose_llm.calls) == 2  # 본문 나열 탐지 → ERROR 피드백 → 같은 턴 내 재호출
    tool_feedback = [m["content"] for m in prose_llm.calls[1] if m["role"] == "tool"]
    assert len(tool_feedback) == 1 and tool_feedback[0].startswith("ERROR:")
    assert "본문" in tool_feedback[0] and "options 배열" in tool_feedback[0]

    s = prose_client.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "awaiting_answers" and s["round_no"] == 1
    q = s["pending_questions"][0]
    assert q["options"][0]["label"] == "레이어드 모놀리식"  # 정규화된 라벨이 카드에 노출


@pytest.fixture()
def rawargs_llm():
    return FakeStreamLLM([
        # 턴1 1호출 — 유효하지 않은 JSON 문자열 인자 (json.loads 실패 → ERROR)
        ("", [("ask_questions", '{"questions": ')]),
        # 턴1 2호출 — 유효 JSON이지만 object가 아닌 인자 (list → ToolError)
        ("", [("ask_questions", ["list"])]),
        # 턴1 3호출 — 정상 인자
        ("", [("ask_questions", {"round_summary": "뼈대 확인",
                                 "questions": [{"text": "청중은 누구인가?",
                                                "options": [{"label": "경영진"},
                                                            {"label": "실무팀"}]}]})]),
    ])


@pytest.fixture()
def raw_app(db_env, test_engine, rawargs_llm):
    from app.main import create_app

    return create_app(start_worker=False, llm_overrides={"interview": rawargs_llm})


@pytest.fixture()
def raw_client(raw_app):
    from fastapi.testclient import TestClient

    with TestClient(raw_app) as c:
        yield c


def test_ask_questions_non_dict_arguments_retry_not_fail(raw_client, rawargs_llm):
    """비-object 도구 인자는 세션 FAILED(튕김) 대신 ERROR 피드백 재시도로 수렴한다."""
    sid = _setup(raw_client)

    events = _sse_events(raw_client, f"/api/interview/sessions/{sid}/kick")
    assert "questions" in [n for n, _ in events]
    assert len(rawargs_llm.calls) == 3
    fb1 = [m["content"] for m in rawargs_llm.calls[1] if m["role"] == "tool"][-1]
    assert fb1.startswith("ERROR: 도구 인자 JSON 파싱 실패")
    fb2 = [m["content"] for m in rawargs_llm.calls[2] if m["role"] == "tool"][-1]
    assert "JSON object여야" in fb2 and "현재 list" in fb2

    s = raw_client.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "awaiting_answers" and s["error"] is None


def test_user_message_is_sent_once_per_turn(sclient, fake_llm):
    """user 메시지는 run_turn이 단일 권위로 적립해 모델 컨텍스트에 1회만 실린다.

    과거 결함: run_turn이 행을 적립한 뒤 autoflush로 _history에 포함되고, 다시
    messages에 재부착해 동일 user 메시지를 모델에 2회 전송했다 (/answers는 선행
    적립까지 겹쳐 이력 행도 2행이었다). 중복은 약한 모델의 직접적인 혼돈 요인이다.
    """
    sid = _setup(sclient)

    _sse_events(sclient, f"/api/interview/sessions/{sid}/kick")
    kicked = [m for m in fake_llm.calls[0]
              if m["role"] == "user" and m["content"].startswith("인터뷰를 시작한다")]
    assert len(kicked) == 1

    _sse_events(sclient, f"/api/interview/sessions/{sid}/answers",
                {"answers": [{"index": 0, "free_text": "경영진 — 도입 승인 판단"}]})
    answered = [m for m in fake_llm.calls[1]
                if m["role"] == "user" and "[라운드 답변]" in m["content"]]
    assert len(answered) == 1

    rows = [m for m in sclient.get(f"/api/interview/sessions/{sid}/messages").json()
            if m["role"] == "user" and "[라운드 답변]" in m["content"]]
    assert len(rows) == 1


def test_system_prompt_carries_fewshot_and_reminder(sclient, fake_llm):
    """시스템 프롬프트는 퓨샷(완성 예시) 섹션 + 매턴 리마인더를 모두 실어 보낸다.

    형태 강제의 프롬프트 쪽 근거: interview.md의 완성 예시 섹션이 본문에, agent.py
    _remind_ask 리마인더가 컨텍스트(응답 직전 위치) 끝에 존재한다. round_summary의
    라운드 번호는 서버가 sess.round_no + 1로 계산해 주입한다 — 모델이 지어내지
    않도록 (kick 시 round_no=0 → 라운드 1).
    """
    sid = _setup(sclient)

    _sse_events(sclient, f"/api/interview/sessions/{sid}/kick")
    sys1 = fake_llm.calls[0][0]["content"]
    assert sys1.startswith("# 인터뷰 에이전트")  # interview.md 전문이 앞쪽
    assert "## ask_questions 인자 형식 (완성 예시)" in sys1
    assert '"allow_free": true' in sys1  # 완성 예시 JSON이 실려 있다
    assert "## 이번 턴 ask_questions 리마인더" in sys1
    assert "라운드 1 목표" in sys1
    assert "suggestions" in sys1          # 추천 후보 계약 서술 (질문 설계 규칙 + 예시)
    assert "모름 답변 처리" in sys1         # 모름 절 신설 (프롬프트 쪽 모름 인지·추천 근거)
    assert "추천 후보" in sys1             # _remind_ask 리마인더 1줄

    _sse_events(sclient, f"/api/interview/sessions/{sid}/answers",
                {"answers": [{"index": 0, "free_text": "경영진"}]})
    sys2 = fake_llm.calls[1][0]["content"]
    assert "라운드 2 목표" in sys2  # 라운드 진행 → 서버 계산 번호 증가


def test_round_summary_persisted_and_replayed(sclient, fake_llm):
    """라운드 목표(round_summary)는 세션에 영속·SessionOut으로 노출되고, 이력
    questions EVENT 행 payload에도 summary가 실린다 — 재접속 리플레이(D6)에서
    라운드 목표가 보존된다 (과거에는 이력 행에서 유실됐다)."""
    sid = _setup(sclient)

    events = _sse_events(sclient, f"/api/interview/sessions/{sid}/kick")
    qev = next(p for n, p in events if n == "questions")
    assert qev["summary"] == "뼈대 확인"  # 라이브 SSE payload

    s = sclient.get(f"/api/interview/sessions/{sid}").json()
    assert s["pending_round_summary"] == "뼈대 확인"  # 세션 영속 → SessionOut 노출

    rows = [m for m in sclient.get(f"/api/interview/sessions/{sid}/messages").json()
            if m["kind"] == "questions"]
    assert len(rows) == 1 and rows[0]["payload"]["summary"] == "뼈대 확인"


TOC_BAD_KEY_MARKDOWN = (
    "# 기획 (치트시트 검증)\n"
    "\n## 메타\n- 목적: x\n"
    "\n## 핵심 메시지 (3개)\n1. a\n2. b\n3. c\n"
    "\n## 슬라이드 목록\n"
    "\n### 1. [유형: 표지] 표지\n- 핵심문장: 표지다\n"
    "\n### 2. [유형: 목차] 목차\n- 내용: 01 배경 및 필요성 / 02 주요 기능 / 03 기대 효과\n"
    "\n### 3. [유형: 마무리] 마무리\n- 핵심문장: 끝\n"
)


def test_plan_format_feedback_carries_remedy(sclient, fake_llm):
    """실세션 위반(목차를 `- 내용:` 임의 키로) 재현 — 포맷 실패 피드백에 파서 원문 +
    치료안 치트시트가 붙고, 재시도 1회에 수렴한다 (계약: 실패 수업 참조)."""
    fake_llm.turns = [
        ("", [("ask_questions", {"questions": [{"text": "q", "allow_free": True}]})]),
        ("", [("save_facts", {"facts": [{"content": "f1", "source": "인터뷰"}]})]),
        ("", [("confirm_key_messages", {"messages": ["a", "b", "c"]})]),
        ("", [("write_plan", {"markdown": TOC_BAD_KEY_MARKDOWN})]),   # 검증 실패
        ("", [("write_plan", {"markdown": plan_sample_markdown()})]),
    ]
    sid = _setup(sclient)
    _sse_events(sclient, f"/api/interview/sessions/{sid}/kick")
    _sse_events(sclient, f"/api/interview/sessions/{sid}/answers",
                {"answers": [{"index": 0, "free_text": "답"}]})
    _sse_events(sclient, f"/api/interview/sessions/{sid}/facts/confirm", {"approve": True})
    events = _sse_events(sclient, f"/api/interview/sessions/{sid}/key-messages",
                         {"approve": True})
    assert len(fake_llm.calls) == 5                       # 실패 1회 → 재시도 1회에 수렴
    fb = [m["content"] for m in fake_llm.calls[4] if m["role"] == "tool"][-1]
    assert fb.startswith("ERROR: plan 포맷 검증 실패")
    assert "슬라이드 2: 해석할 수 없는 불릿입니다: 내용:" in fb  # 파서 원문 그대로 (변경 없음)
    assert "치트시트" in fb
    assert "핵심문장: 01 배경 및 필요성 / 02 주요 기능 / 03 기대 효과" in fb  # 모범 표기
    assert "- 표: [항목 | 형식 | 상태]" in fb              # 표 행 교정 예 — 치트시트에서만 나온다
    assert "plan_draft" in [n for n, _ in events]
    s = sclient.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "plan_review" and s["error"] is None


SKELETON_MISSING_MARKDOWN = (
    "# 기획 (골격 미달)\n"
    "\n## 메타\n- 목적: x\n"
    "\n## 핵심 메시지 (3개)\n1. a\n2. b\n3. c\n"
    "\n## 슬라이드 목록\n"
    "\n### 1. [유형: 표] 데이터\n- 표: [항목 | 값]\n  - 항목1 | 1\n"
)


def test_plan_skeleton_error_feedback_loops_back(sclient, fake_llm):
    """골격 미달(SkeletonError)도 ERROR 피드백으로 돌아와 재시도에 참여한다 — 과거에는
    except PlanError가 놓쳐 피드백 없이 세션이 즉시 FAILED였다."""
    fake_llm.turns = [
        ("", [("ask_questions", {"questions": [{"text": "q", "allow_free": True}]})]),
        ("", [("save_facts", {"facts": [{"content": "f1", "source": "인터뷰"}]})]),
        ("", [("confirm_key_messages", {"messages": ["a", "b", "c"]})]),
        ("", [("write_plan", {"markdown": SKELETON_MISSING_MARKDOWN})]),  # 골격 미달
        ("", [("write_plan", {"markdown": plan_sample_markdown()})]),
    ]
    sid = _setup(sclient)
    _sse_events(sclient, f"/api/interview/sessions/{sid}/kick")
    _sse_events(sclient, f"/api/interview/sessions/{sid}/answers",
                {"answers": [{"index": 0, "free_text": "답"}]})
    _sse_events(sclient, f"/api/interview/sessions/{sid}/facts/confirm", {"approve": True})
    events = _sse_events(sclient, f"/api/interview/sessions/{sid}/key-messages",
                         {"approve": True})
    assert len(fake_llm.calls) == 5
    fb = [m["content"] for m in fake_llm.calls[4] if m["role"] == "tool"][-1]
    assert fb.startswith("ERROR: plan 골격 검증 실패")
    assert "문서 '제안서'" in fb                      # 메타에 산출 문서 생략 → docs 기본값
    assert "표지, 목차, 마무리" in fb                # validate_skeleton 원문 유지 (filter.py)
    assert "write_plan을 다시 호출하라" in fb        # 재시도 참여 안내
    assert "plan_draft" in [n for n, _ in events]
    s = sclient.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "plan_review" and s["error"] is None


DOC_TAG_META_MISSING_MARKDOWN = (
    "# 기획 (메타 누락)\n"
    "\n## 메타\n- 목적: x\n"
    "\n## 핵심 메시지 (3개)\n1. a\n2. b\n3. c\n"
    "\n## 슬라이드 목록\n"
    "\n### 1. [유형: 표지][문서: 제안서] 표지\n- 핵심문장: 표지다\n"
    "\n### 2. [유형: 표지][문서: 개발설계서] 개발 표지\n- 핵심문장: 표지다\n"
)


def test_plan_doc_tag_mismatch_feedback_loops_back(sclient, fake_llm):
    """다중 문서 plan의 메타 '산출 문서' 누락(태그는 정상 — 실세션 수업)을 파서 교차검증이
    막는다: 디폴트 ["제안서"] 무음 치환 대신 PlanError가 치트시트와 함께 ERROR 피드백으로
    돌아와 재시도에 참여한다."""
    fake_llm.turns = [
        ("", [("ask_questions", {"questions": [{"text": "q", "allow_free": True}]})]),
        ("", [("save_facts", {"facts": [{"content": "f1", "source": "인터뷰"}]})]),
        ("", [("confirm_key_messages", {"messages": ["a", "b", "c"]})]),
        ("", [("write_plan", {"markdown": DOC_TAG_META_MISSING_MARKDOWN})]),  # 교차검증 실패
        ("", [("write_plan", {"markdown": plan_sample_markdown()})]),
    ]
    sid = _setup(sclient)
    _sse_events(sclient, f"/api/interview/sessions/{sid}/kick")
    _sse_events(sclient, f"/api/interview/sessions/{sid}/answers",
                {"answers": [{"index": 0, "free_text": "답"}]})
    _sse_events(sclient, f"/api/interview/sessions/{sid}/facts/confirm", {"approve": True})
    events = _sse_events(sclient, f"/api/interview/sessions/{sid}/key-messages",
                         {"approve": True})
    assert len(fake_llm.calls) == 5                       # 실패 1회 → 재시도 1회에 수렴
    fb = [m["content"] for m in fake_llm.calls[4] if m["role"] == "tool"][-1]
    assert fb.startswith("ERROR: plan 포맷 검증 실패")
    assert "슬라이드 문서 태그 '개발설계서'가 메타 '산출 문서'(제안서)에 없습니다" in fb
    assert "'- 산출 문서: 제안서, 개발설계서'" in fb      # 치료안 — 필요 표기 안내
    assert "치트시트" in fb
    assert "plan_draft" in [n for n, _ in events]
    s = sclient.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "plan_review" and s["error"] is None


def test_plan_retry_exhaustion_marks_session_failed(sclient, fake_llm):
    """write_plan 실패 3회 소진 — 4번째 write_plan 호출에서 dispatch_blocking 가드가
    TurnError로 세션 FAILED를 남긴다 (SSE error 이벤트 + 세션 error 문자열)."""
    bad = "# 기획\n\n## 메타\n- 목적: x\n\n## 핵심 메시지 (3개)\n1. a\n\n## 슬라이드 목록\n"
    fake_llm.turns = [
        ("", [("ask_questions", {"questions": [{"text": "q", "allow_free": True}]})]),
        ("", [("save_facts", {"facts": [{"content": "f1", "source": "인터뷰"}]})]),
        ("", [("confirm_key_messages", {"messages": ["a", "b", "c"]})]),
        ("", [("write_plan", {"markdown": bad})]),   # 실패 1
        ("", [("write_plan", {"markdown": bad})]),   # 실패 2
        ("", [("write_plan", {"markdown": bad})]),   # 실패 3
        ("", [("write_plan", {"markdown": bad})]),   # 4호출 — plan_fixes 가드 → TurnError
    ]
    sid = _setup(sclient)
    _sse_events(sclient, f"/api/interview/sessions/{sid}/kick")
    _sse_events(sclient, f"/api/interview/sessions/{sid}/answers",
                {"answers": [{"index": 0, "free_text": "답"}]})
    _sse_events(sclient, f"/api/interview/sessions/{sid}/facts/confirm", {"approve": True})
    events = _sse_events(sclient, f"/api/interview/sessions/{sid}/key-messages",
                         {"approve": True})
    names = [n for n, _ in events]
    assert "plan_draft" not in names
    err = next(p for n, p in events if n == "error")
    assert err["message"] == "plan 검증 재시도 한도 초과"
    assert len(fake_llm.calls) == 7  # 게이트 3회 + write_plan 4회 — MAX_TOOL_TURNS(8) 이내, plan 가드가 먼저 끊는다
    s = sclient.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "failed" and s["status"] == "aborted"
    assert "plan 검증 재시도 한도 초과" in (s["error"] or "")


# ---------------------------------------------------------------------------
# 답변 추천(모름 처리) — 문항 suggestions 칩 + 미제출 (모름) 마킹 + (미확정) 팩트 적립


RECOMMENDED_FACT = ("주요 고객: 사내 경영진·현업 부서 (미확정) — "
                    "소스 '보고 개선안'의 '매출·실무 부서 대상' 표기에 근거")


@pytest.fixture()
def sg_llm():
    return FakeStreamLLM([
        # 턴1 kick: 2문항 — 문항1 서술형+suggestions, 문항2 객관형
        ("가설 초안: 보고 업무 자동화.", [
            ("ask_questions", {"round_summary": "뼈대 확인",
                               "questions": [
                                   {"text": "주요 고객은 누구인가?", "allow_free": True,
                                    "suggestions": ["사내 경영진·현업 부서 (미확정)",
                                                    "외부 고객사 (미확정)"]},
                                   {"text": "언제까지 제출해야 하나요?", "options": [
                                       {"label": "4월 말"},
                                       {"label": "5월 말"}]},
                               ]}),
        ]),
        # 턴2 (라운드 답변에 (모름) 있음): 근거 기반 추천 후보를 (미확정) 팩트로 save_facts —
        # interview.md "모름 답변 처리" 절이 유도하는 동작
        ("", [
            ("save_facts", {"facts": [
                {"content": RECOMMENDED_FACT, "source": "인터뷰 추천"}]}),
        ]),
        # 턴3 (팩트 승인 후): 남은 항목을 이어서 진행 (라운드 2)
        ("", [
            ("ask_questions", {"round_summary": "라운드 2 목표: 일정 확정",
                               "questions": [{"text": "제출 일정은 어떻게 되나요?",
                                              "allow_free": True}]}),
        ]),
    ])


@pytest.fixture()
def sg_app(db_env, test_engine, sg_llm):
    from app.main import create_app

    return create_app(start_worker=False, llm_overrides={"interview": sg_llm})


@pytest.fixture()
def sg_client(sg_app):
    from fastapi.testclient import TestClient

    with TestClient(sg_app) as c:
        yield c


def test_suggestions_flow_to_card_payload(sg_client):
    """suggestions는 pending_questions(SessionOut)와 questions 이벤트 payload로
    프론트 답변 카드까지 전달된다 (unknown[] 타입이라 openapi 계약은 무변경)."""
    sid = _setup(sg_client)

    events = _sse_events(sg_client, f"/api/interview/sessions/{sid}/kick")
    qev = next(p for n, p in events if n == "questions")
    assert qev["questions"][0]["suggestions"] == ["사내 경영진·현업 부서 (미확정)",
                                                  "외부 고객사 (미확정)"]
    s = sg_client.get(f"/api/interview/sessions/{sid}").json()
    assert s["pending_questions"][0]["suggestions"] == ["사내 경영진·현업 부서 (미확정)",
                                                        "외부 고객사 (미확정)"]
    assert s["pending_questions"][1].get("suggestions") is None  # 선택 필드 — 미제시 통과


def test_answers_lines_are_index_sorted_and_unanswered_marked(sg_client, sg_llm):
    """답변 라인은 인덱스 오름차순으로 정렬되고, 제출 순서와 무관하다."""
    sid = _setup(sg_client)
    _sse_events(sg_client, f"/api/interview/sessions/{sid}/kick")

    _sse_events(sg_client, f"/api/interview/sessions/{sid}/answers",
                {"answers": [{"index": 1, "option": 0},
                             {"index": 0, "free_text": "사내 경영진"}]})
    answered = [m["content"] for m in sg_llm.calls[1]
                if m["role"] == "user" and "[라운드 답변]" in m["content"]]
    assert len(answered) == 1
    assert "1. 주요 고객은 누구인가?\n→ 사내 경영진" in answered[0]
    assert "2. 언제까지 제출해야 하나요?\n→ 4월 말" in answered[0]
    assert answered[0].index("1. ") < answered[0].index("2. ")  # 역순 제출 → 정렬 조립
    assert "→ (모름)" not in answered[0]


def test_unanswered_question_marked_and_recommended_fact_staged(sg_client, sg_llm, db_env):
    """모름 경로 e2e — 미제출 문항은 → (모름) 마킹, 다음 턴에서 근거 기반 추천이
    (미확정) 팩트(fact_gate)로 제시되고, 승인 시 팩트 저장소에 origin=interview로
    적립되며 라운드가 이어진다."""
    sid = _setup(sg_client)
    _sse_events(sg_client, f"/api/interview/sessions/{sid}/kick")

    # 문항 1 (인덱스 0)은 무응답 — 서버가 → (모름) 마킹
    _sse_events(sg_client, f"/api/interview/sessions/{sid}/answers",
                {"answers": [{"index": 1, "option": 0}]})
    answered = [m["content"] for m in sg_llm.calls[1]
                if m["role"] == "user" and "[라운드 답변]" in m["content"]]
    assert "1. 주요 고객은 누구인가?\n→ (모름)" in answered[0]
    assert "2. 언제까지 제출해야 하나요?\n→ 4월 말" in answered[0]

    # 추천 팩트 제시 → fact_gate에서 '인터뷰 추천' 출처가 그대로 노출된다
    s = sg_client.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "fact_gate"
    assert s["pending_facts"][0]["source"] == "인터뷰 추천"
    assert "(미확정)" in s["pending_facts"][0]["content"]

    # 승인 시에만 적립 (원칙 4) — content·source 원문 보존
    _sse_events(sg_client, f"/api/interview/sessions/{sid}/facts/confirm", {"approve": True})
    facts = sg_client.get("/api/projects/1/facts").json()
    listed = [f for f in facts if f["source"] == "인터뷰 추천"]
    assert len(listed) == 1 and listed[0]["origin"] == "interview"
    assert listed[0]["content"] == RECOMMENDED_FACT  # 한 글자도 다르게 복사되지 않는다

    # 추천 후보가 다음 턴을 막지 않는다 — 승인 스트림 내에서 다음 턴이 실행돼 라운드 2 질문이 진행된다
    s = sg_client.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "awaiting_answers" and s["round_no"] == 2


def test_empty_answers_rejected_with_409(sg_client, sg_llm):
    """빈 answers 배열은 409 — LLM 턴이 열리지 않고 세션 상태가 보존된다
    (프론트 1개 이상 강제의 서버 쪽 대응)."""
    sid = _setup(sg_client)
    _sse_events(sg_client, f"/api/interview/sessions/{sid}/kick")

    before = len(sg_llm.calls)
    r = sg_client.post(f"/api/interview/sessions/{sid}/answers", json={"answers": []})
    assert r.status_code == 409
    s = sg_client.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "awaiting_answers" and s["round_no"] == 1
    assert s["error"] is None
    assert len(sg_llm.calls) == before  # LLM 턴 미개시


@pytest.fixture()
def sug_retry_llm():
    return FakeStreamLLM([
        # 턴1 1호출 — 추천 후보 4개 (validate_tool_args 실패 → ERROR)
        ("", [("ask_questions", {"round_summary": "뼈대 확인",
                                 "questions": [{"text": "고객은 누구인가?", "allow_free": True,
                                                "suggestions": ["a", "b", "c", "d"]}]})]),
        # 턴1 2호출 — ERROR 피드백을 받아 2개로 줄여 재호출
        ("", [("ask_questions", {"round_summary": "뼈대 확인",
                                 "questions": [{"text": "고객은 누구인가?", "allow_free": True,
                                                "suggestions": ["a", "b"]}]})]),
    ])


@pytest.fixture()
def sug_retry_app(db_env, test_engine, sug_retry_llm):
    from app.main import create_app

    return create_app(start_worker=False, llm_overrides={"interview": sug_retry_llm})


@pytest.fixture()
def sug_retry_client(sug_retry_app):
    from fastapi.testclient import TestClient

    with TestClient(sug_retry_app) as c:
        yield c


def test_ask_questions_suggestions_contract_triggers_retry(sug_retry_client, sug_retry_llm):
    sid = _setup(sug_retry_client)

    events = _sse_events(sug_retry_client, f"/api/interview/sessions/{sid}/kick")
    assert "questions" in [n for n, _ in events]
    assert len(sug_retry_llm.calls) == 2  # 추천 후보 위반 → ERROR 피드백 → 같은 턴 내 재호출
    tool_feedback = [m["content"] for m in sug_retry_llm.calls[1] if m["role"] == "tool"]
    assert len(tool_feedback) == 1 and tool_feedback[0].startswith("ERROR:")
    assert f"최대 {MAX_SUGGESTIONS}개" in tool_feedback[0]

    s = sug_retry_client.get(f"/api/interview/sessions/{sid}").json()
    assert s["phase"] == "awaiting_answers" and s["round_no"] == 1
    assert s["pending_questions"][0]["suggestions"] == ["a", "b"]