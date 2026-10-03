# -*- coding: utf-8 -*-
"""app.agents.tools.validate_tool_args 검증 테스트 — 문항별 선택지 계약 강제.

계약: 각 문항은 options 2개 이상 또는 allow_free=true 중 하나를 반드시 갖는다
(둘 다 있어도 된다). 위반 시 ToolError → 콜백 ERROR 피드백으로 LLM 재호출을 유도한다.
"""
from __future__ import annotations

import pytest

from app.agents.tools import MAX_QUESTIONS, ToolError, validate_tool_args


def _q(**extra):
    return {"text": "질문?", **extra}


def test_two_options_passes():
    args = {"questions": [_q(options=[{"label": "경영진"}, {"label": "실무팀"}])]}
    assert validate_tool_args("ask_questions", args) == args
    # 둘 다 있어도 된다 — 선택지 카드 + 직접입력 동시 노출
    both = {"questions": [_q(options=[{"label": "가"}, {"label": "나"}], allow_free=True)]}
    assert validate_tool_args("ask_questions", both) == both


def test_single_option_rejected():
    with pytest.raises(ToolError, match="2개 이상"):
        validate_tool_args("ask_questions", {"questions": [_q(options=[{"label": "가"}])]})


def test_free_text_requires_explicit_allow_free():
    ok = {"questions": [_q(allow_free=True)]}
    assert validate_tool_args("ask_questions", ok) == ok
    with pytest.raises(ToolError, match="선택지가 없습니다"):
        validate_tool_args("ask_questions", {"questions": [_q()]})
    with pytest.raises(ToolError, match="allow_free"):
        validate_tool_args("ask_questions", {"questions": [{"text": "질문?", "allow_free": False}]})


def test_error_message_names_the_question_index():
    qs = [_q(allow_free=True), _q()]
    with pytest.raises(ToolError, match="문항 2"):
        validate_tool_args("ask_questions", {"questions": qs})


def test_empty_and_too_many_questions_still_rejected():
    with pytest.raises(ToolError, match="비어"):
        validate_tool_args("ask_questions", {"questions": []})
    with pytest.raises(ToolError, match=f"최대 {MAX_QUESTIONS}문항"):
        validate_tool_args("ask_questions", {
            "questions": [_q(allow_free=True)] * (MAX_QUESTIONS + 1)})


def test_non_dict_question_rejected():
    with pytest.raises(ToolError, match="문항 1"):
        validate_tool_args("ask_questions", {"questions": ["질문 문자열?"]})


def test_other_tools_unaffected():
    assert validate_tool_args("save_facts", {"facts": [{"content": "x"}]}) == {
        "facts": [{"content": "x"}]}
    assert validate_tool_args("update_checklist", {"items": []}) == {"items": []}
    with pytest.raises(ToolError, match="3개"):
        validate_tool_args("confirm_key_messages", {"messages": ["a", "b"]})