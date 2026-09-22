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