# -*- coding: utf-8 -*-
"""테스트용 가짜 LLM — test_derive.py의 FakeLLM 패턴을 API 테스트에서도 쓰기 위해 분리."""
from __future__ import annotations

from pathlib import Path


class FakeLLM:
    """스크립트된 응답을 순서대로 반환하는 가짜 chat_fn. 받은 messages를 기록한다."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    def __call__(self, messages, tools=None):
        self.calls.append([dict(m) for m in messages])
        return self.responses.pop(0)


def tool_call(name: str, payload: dict) -> dict:
    return {"content": None, "tool_calls": [{"name": name, "arguments": payload}]}


def correct_slides_payload() -> dict:
    """plan.sample.md의 제안서 슬라이드에 대한 유효한 slides.json 변환."""
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


def correct_report_payload() -> dict:
    """plan.sample.md의 제안서에 대한 유효한 report.json 변환 (문서체 재구성)."""
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


def plan_sample_markdown() -> str:
    return (Path(__file__).parent / "fixtures" / "plan.sample.md").read_text(encoding="utf-8-sig")

class FakeStreamLLM:
    """stream_fn 계약(provider.stream) 가짜 — 인터뷰 에이전트 턴 스크립트.

    turns: [(text, [(name, args), ...]), ...] — LLM 호출 1회분 = 텍스트 + 도구 호출들.
    """

    def __init__(self, turns):
        self.turns = list(turns)
        self.calls: list[list[dict]] = []

    def stream(self, messages, tools=None):
        self.calls.append(list(messages))
        if not self.turns:
            raise AssertionError("스크립트된 턴을 모두 소진했습니다")
        text, calls = self.turns.pop(0)
        if text:
            yield {"type": "text", "delta": text}
        for name, args in calls:
            yield {"type": "tool_call", "name": name, "arguments": args}
