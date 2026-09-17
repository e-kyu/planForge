# -*- coding: utf-8 -*-
"""derive 오케스트레이터 테스트 — 가짜 LLM을 주입해 결정론 파이프라인(검증·수치 게이트·재시도·기록)을 잠근다."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from reportagent.derive import Deriver, DeriveError, render_slides_text
from reportagent.plan import filter_slides, parse_plan_file

FIX = Path(__file__).parent / "fixtures"
PLAN = FIX / "plan.sample.md"


class FakeLLM:
    """스크립트된 응답을 순서대로 반환하는 가짜 chat_fn. 받은 messages를 기록한다."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    def __call__(self, messages, tools=None):
        self.calls.append([dict(m) for m in messages])
        return self.responses.pop(0)


def tool_call(name, payload):
    return {"content": None, "tool_calls": [{"name": name, "arguments": payload}]}


# ---------------------------------------------------------------- 슬라이드 파생

def correct_slides_payload():
    return {
        "meta": {"title": "업무 자동화 도입 제안", "subtitle": "반복 보고 업무의 효율화 방안"},
        "slides": [
            {"type": "cover", "title": "업무 자동화 도입 제안", "subtitle": "반복 보고 업무의 자동화로 주 11.5시간을 절감한다"},
            {"type": "toc", "title": "목차", "bullets": [
                {"label": "01", "body": "현황 및 문제점"},
                {"label": "02", "body": "시스템 구성"},
                {"label": "03", "body": "기대 효과 및 요청 사항"},
            ]},
            {"type": "two-col", "title": "현황 및 문제점",
             "left": {"heading": "현황", "bullets": [
                 {"label": "보고 작성", "body": "주 10시간 수기 작성"},
                 {"label": "데이터 취합", "body": "부서별 양식 상이로 수작업 취합"}]},
             "right": {"heading": "문제점", "bullets": [
                 {"label": "시간 낭비", "body": "단순 반복 업무에 인력 소모"},
                 {"label": "오류 위험", "body": "수기 전사 과정에서 실수 발생"}]}},
            {"type": "arch", "title": "시스템 구성도", "arch": {"groups": [
                {"name": "사용자 계층", "items": ["보고 작성 화면", "관리자 화면"]},
                {"name": "서비스 계층", "items": ["보고 생성 서비스", "데이터 취합 서비스"]},
                {"name": "데이터 계층", "items": ["보고 DB", "템플릿 저장소"]},
            ]}},
            {"type": "closing", "title": "기대 효과 및 요청 사항", "bullets": [
                {"label": "효과", "body": "주 11.5시간 절감"},
                {"label": "품질", "body": "수기 오류 제거"},
            ], "note": "요청: 4분기 시범 도입 승인"},
        ],
    }


def test_derive_slides_success(tmp_path):
    llm = FakeLLM([tool_call("write_slides_json", correct_slides_payload())])
    ws = tmp_path / "ws"
    res = Deriver(llm, ws).derive(PLAN, "slides", "제안서")
    assert res.slides_count == 5 and res.attempts == 1
    payload = json.loads(res.work_path.read_text(encoding="utf-8"))
    assert payload["meta"]["title"] == "업무 자동화 도입 제안"  # 결정론 보정: 표지 제목
    # SSOT: work/slides.json에 기록됨
    assert res.work_path == ws / "work" / "slides.json"


def test_derive_numeric_gate_retries_then_succeeds(tmp_path):
    bad = correct_slides_payload()
    bad["slides"][4]["bullets"][0]["body"] = "주 12시간 절감"  # 11.5 왜곡 주입 (수용 기준 3)
    llm = FakeLLM([
        tool_call("write_slides_json", bad),
        tool_call("write_slides_json", correct_slides_payload()),
    ])
    res = Deriver(llm, tmp_path).derive(PLAN, "slides", "제안서")
    assert res.attempts == 2
    # 재시도 피드백에 🔴 발견사항이 전달됐는지
    retry_user = llm.calls[1][-1]["content"]
    assert "수치 무결성 검증 실패" in retry_user and "12" in retry_user


def test_derive_schema_violation_retries():
    bad = {"meta": {"title": "제목"}, "slides": [{"type": "unknown", "title": "x"}]}
    llm = FakeLLM([
        tool_call("write_slides_json", bad),
        tool_call("write_slides_json", correct_slides_payload()),
    ])
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        res = Deriver(llm, td).derive(PLAN, "slides", "제안서")
        assert res.attempts == 2
        retry_user = llm.calls[1][-1]["content"]
        assert "스키마 검증 실패" in retry_user


def test_derive_gives_up_after_max_attempts():
    bad = correct_slides_payload()
    bad["slides"][4]["bullets"][0]["body"] = "주 12시간 절감"
    llm = FakeLLM([tool_call("write_slides_json", bad) for _ in range(3)])
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        with pytest.raises(DeriveError, match="수치 무결성"):
            Deriver(llm, td).derive(PLAN, "slides", "제안서")


# ---------------------------------------------------------------- 문서 파생 (문서체 재구성)

def correct_report_payload():
    return {
        "meta": {"title": "업무 자동화 도입 제안", "doc_type": "제안서"},
        "sections": [
            {"type": "header", "title": "업무 자동화 도입 제안",
             "subtitle": "반복 보고 업무의 자동화로 주 11.5시간을 절감한다"},
            {"type": "overview", "title": "개요", "items": [
                {"no": "01", "label": "현황 및 문제점", "body": "보고 작성이 수기 작업으로 진행되며 양식 상이로 취합이 수작업이다."},
                {"no": "02", "label": "시스템 구성", "body": "사용자·서비스·데이터 계층으로 구성된다."},
                {"no": "03", "label": "기대 효과 및 요청 사항", "body": "주 11.5시간 절감과 수기 오류 제거를 기대하며 시범 도입을 요청한다."}]},
            {"type": "section", "no": "1", "title": "현황 및 문제점",
             "blocks": [
                 {"kind": "prose", "heading": "현황", "paragraphs": [
                     "보고 작성은 주 10시간 수기 작성으로 진행되고, 데이터 취합은 부서별 양식 상이로 수작업 취합된다."]},
                 {"kind": "prose", "heading": "문제점", "paragraphs": [
                     "단순 반복 업무에 인력이 소모되고, 수기 전사 과정에서 실수가 발생한다."]}],
             "source": "interview-log [2026-09-09] 해결 문제 (샘플)"},
            {"type": "section", "no": "2", "title": "시스템 구성도",
             "blocks": [{"kind": "table", "heading": "시스템 구성", "headers": ["계층", "구성요소"], "rows": [
                 ["사용자 계층", "보고 작성 화면, 관리자 화면"],
                 ["서비스 계층", "보고 생성 서비스, 데이터 취합 서비스"],
                 ["데이터 계층", "보고 DB, 템플릿 저장소"]]}],
             "source": "interview-log [2026-09-09] 시스템 구성 확정 (샘플)"},
            {"type": "conclusion", "title": "기대 효과 및 요청 사항", "paragraphs": [
                "주 11.5시간 절감 + 수기 오류 제거의 효과가 기대된다."],
             "requests": ["4분기 시범 도입 승인"], "note": ""},
        ],
    }


def test_derive_report_success_and_build(tmp_path):
    llm = FakeLLM([tool_call("write_report_json", correct_report_payload())])
    res = Deriver(llm, tmp_path).derive(PLAN, "report", "제안서")
    assert res.sections_count == 5 and res.attempts == 1
    outs = Deriver(llm, tmp_path).build("report", ("md",))
    md = [p for p in outs if p.suffix == ".md"]
    assert md and "_v01" in md[0].name
    text = md[0].read_text(encoding="utf-8")
    assert "11.5시간" in text and "10시간" in text  # 수치 유지


def test_derive_rejects_doc_not_in_plan(tmp_path):
    llm = FakeLLM([])
    from reportagent.plan import PlanError
    with pytest.raises(PlanError, match="산출 문서"):
        Deriver(llm, tmp_path).derive(PLAN, "slides", "보고서")


def test_render_slides_text_verbatim():
    plan = parse_plan_file(PLAN)
    slides = filter_slides(plan.slides, "제안서")
    text = render_slides_text(plan, slides, "제안서")
    assert "주 11.5시간을 되찾는다" in text                     # 핵심 메시지 무변경
    assert "보고 작성 | 주 10시간 수기 작성" in text            # 2단 표기 무변경
    assert "사용자 계층 | 보고 작성 화면, 관리자 화면" in text   # 구성 표기 무변경
    assert "interview-log [2026-09-09] 효과 수치 정책 (샘플)" in text  # 근거 무변경


# ---------------------------------------------------------------- provider 설정

def test_load_config_profiles():
    from reportagent.llm import load_config
    profiles = load_config(Path(__file__).parent.parent / "backend" / "reportagent" / "llm" / "config.example.json")
    assert set(profiles) == {"interview", "derive", "review"}
    assert profiles["derive"].provider == "ollama"
    assert profiles["derive"].model == "gemma4:26b"


def test_provider_requires_model():
    from reportagent.llm import ProfileConfig, get_provider
    with pytest.raises(ValueError, match="모델"):
        get_provider(ProfileConfig(provider="ollama", model=""))


def test_config_file_missing_message(tmp_path, monkeypatch):
    """config.json이 없으면 안내와 함께 exit 2 (cmd_derive 레벨)."""
    from reportagent import __main__ as m
    ns = m.argparse.Namespace(plan=str(PLAN), workspace=str(tmp_path), kind="slides",
                              doc=None, fmts=None, no_build=True, allow_unconfirmed=False,
                              config=str(tmp_path / "none.json"))
    assert m.cmd_derive(ns) == 2