# -*- coding: utf-8 -*-
"""app.agents.tools.validate_tool_args 검증 테스트 — 문항별 선택지 계약 강제.

계약: 각 문항은 options 2개 이상 또는 allow_free=true 중 하나를 반드시 갖는다
(둘 다 있어도 된다). 위반 시 ToolError → 콜백 ERROR 피드백으로 LLM 재호출을 유도한다.
"""
from __future__ import annotations

import pytest

from app.agents.tools import (MAX_QUESTIONS, MAX_SUGGESTIONS,
                              SUGGESTION_MAX_LEN, ToolError, _prose_option_lines,
                              validate_tool_args)


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


# ---------------------------------------------------------------------------
# 본문 서술형 선택지 나열 탐지 — 선택지는 options 배열로만 전달하는 계약


def test_prose_choice_lines_heuristic_variants():
    assert _prose_option_lines("질문:\n예:\n- 레이어드 모놀리식\n- 마이크로서비스") == [
        "예:", "- 레이어드 모놀리식", "- 마이크로서비스"]
    assert _prose_option_lines("1. 선택\n2. 선택") == ["1. 선택", "2. 선택"]
    assert _prose_option_lines("가) 안내\n나) 안내") == ["가) 안내", "나) 안내"]
    assert _prose_option_lines("① 안내\n② 안내") == ["① 안내", "② 안내"]
    assert _prose_option_lines("(1) 안내\n(가) 안내") == ["(1) 안내", "(가) 안내"]
    assert _prose_option_lines("선택지: A\n선택지: B") == ["선택지: A", "선택지: B"]
    # JSON 문자열에 실린 리터럴 \n도 줄 분리한다
    assert _prose_option_lines("예:\\n- A\\n- B") == ["예:", "- A", "- B"]


def test_prose_choices_rejected_with_feedback():
    bad_text = "시스템 구조는 어떻게 잡나요?\n예:\n- 레이어드 모놀리식\n- 마이크로서비스"
    with pytest.raises(ToolError, match="options 배열"):
        validate_tool_args("ask_questions", {"questions": [
            {"text": bad_text, "allow_free": True}]})
    # 여러 문항을 한 번에 지적 — 재시도 1회로 수렴시킨다
    with pytest.raises(ToolError) as e:
        validate_tool_args("ask_questions", {"questions": [
            {"text": bad_text, "allow_free": True},
            {"text": "보조 질문?", "allow_free": True},
            {"text": "질문?\n1. 안내\n2. 안내", "allow_free": True}]})
    assert "문항 1" in str(e.value) and "문항 3" in str(e.value)


def test_prose_choices_threshold_and_false_positives():
    ok_texts = [
        "예: A/B 형식으로 구체적으로 답해주세요",   # 한 줄 예시 힌트
        "1) 목표 시점 2) 제출 기한",                 # 한 줄 인라인 나열
        "예시: 주 10시간 같은 정량 표현",            # 예시: — 옵션 마커 아님
        "2024. 3분기 매출은 어떤가요?",              # 수치 + 조사 (번호 마커 아님)
        "청중은 누구인가?",
        "시스템 구조는 어떻게 잡나요?",
        "언어·프레임워크·버전과 패키지 구조는?",
    ]
    for t in ok_texts:
        args = {"questions": [{"text": t, "allow_free": True},
                              {"text": "보조 질문?", "allow_free": True}]}
        assert validate_tool_args("ask_questions", args) == args


def test_option_labels_normalized_or_rejected():
    args = {"questions": [{"text": "질문?", "options": [
        {"label": "  경영진 ", "description": "승인 판단"},
        {"label": "실무팀"}]}]}
    out = validate_tool_args("ask_questions", args)
    assert out["questions"][0]["options"][0]["label"] == "경영진"  # strip 정규화
    assert out["questions"][0]["options"][1]["label"] == "실무팀"  # 깨끗한 라벨 원형 유지
    for bad_opts in ([{"description": "라벨 없음"}, {"label": "실무팀"}],
                     [{"label": ""}, {"label": "실무팀"}],
                     [{"label": "   "}, {"label": "실무팀"}],
                     [{"label": 5}, {"label": "실무팀"}]):
        with pytest.raises(ToolError, match="label이 비어"):
            validate_tool_args("ask_questions", {"questions": [
                {"text": "질문?", "options": bad_opts}]})
    with pytest.raises(ToolError, match="description은 문자열"):
        validate_tool_args("ask_questions", {"questions": [
            {"text": "질문?", "options": [{"label": "경영진", "description": 5},
                                          {"label": "실무팀"}]}]})
    with pytest.raises(ToolError, match="옵션은 object"):
        validate_tool_args("ask_questions", {"questions": [
            {"text": "질문?", "options": ["경영진", {"label": "실무팀"}]}]})


def test_non_dict_args_rejected():
    """비-object 인자는 AttributeError(세션 FAILED 전파)가 아니라 재시도 피드백이다."""
    with pytest.raises(ToolError, match="JSON object여야"):
        validate_tool_args("ask_questions", ["x"])
    with pytest.raises(ToolError, match="JSON object여야"):
        validate_tool_args("write_plan", "not-a-dict")
    with pytest.raises(ToolError, match="현재 int"):
        validate_tool_args("save_facts", 3)


def test_prose_detection_coexists_with_options():
    bad_text = "질문?\n예:\n- A\n- B"
    with pytest.raises(ToolError, match="선택지 나열"):
        validate_tool_args("ask_questions", {"questions": [
            {"text": bad_text, "options": [{"label": "A"}, {"label": "B"}]}]})


# ---------------------------------------------------------------------------
# 추천 후보 칩 계약 — 문항별 suggestions(선택 필드): 문자열 배열, 1~3개, 한 줄


def test_suggestions_optional_and_normalized():
    out = validate_tool_args("ask_questions", {"questions": [
        _q(allow_free=True, suggestions=["  후보 A  ", "후보 B", "후보 C"])]})
    assert out["questions"][0]["suggestions"] == ["후보 A", "후보 B", "후보 C"]  # strip 정규화
    for n in (1, 2):  # 1개·2개도 된다
        out2 = validate_tool_args("ask_questions", {"questions": [
            _q(allow_free=True, suggestions=[f"후보 {k}" for k in range(1, n + 1)])]})
        assert len(out2["questions"][0]["suggestions"]) == n
    # 객관형 문항에도 실 수 있다 (추천이 옵션 라벨과 같아도 무해 — 중복 금지 없음)
    both = {"questions": [_q(options=[{"label": "a"}, {"label": "b"}],
                             suggestions=["후보 A"])]}
    assert validate_tool_args("ask_questions", both) == both


def test_suggestions_empty_string_rejected():
    with pytest.raises(ToolError, match="후보가 비어"):
        validate_tool_args("ask_questions", {"questions": [
            _q(allow_free=True, suggestions=["후보 A", "   "])]})


def test_suggestions_non_string_item_rejected():
    with pytest.raises(ToolError, match="문자열이어야"):
        validate_tool_args("ask_questions", {"questions": [
            _q(allow_free=True, suggestions=["후보 A", 5])]})


def test_suggestions_over_max_rejected():
    sugs = [f"후보 {k}" for k in range(MAX_SUGGESTIONS + 1)]  # 4개
    with pytest.raises(ToolError, match=f"최대 {MAX_SUGGESTIONS}개"):
        validate_tool_args("ask_questions", {"questions": [
            _q(allow_free=True, suggestions=sugs)]})


def test_suggestions_newline_rejected_literal_and_escaped():
    for sug in ("후보 A\n후보 B", "후보 A\\n후보 B"):
        with pytest.raises(ToolError, match="한 줄"):
            validate_tool_args("ask_questions", {"questions": [
                _q(allow_free=True, suggestions=[sug])]})


def test_suggestions_too_long_rejected():
    sug = "가" * (SUGGESTION_MAX_LEN + 1)
    with pytest.raises(ToolError, match=f"{SUGGESTION_MAX_LEN}자 이내"):
        validate_tool_args("ask_questions", {"questions": [
            _q(allow_free=True, suggestions=[sug])]})


def test_suggestions_non_list_rejected():
    with pytest.raises(ToolError, match="문자열 배열이어야"):
        validate_tool_args("ask_questions", {"questions": [
            _q(allow_free=True, suggestions="후보 A")]})