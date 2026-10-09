# -*- coding: utf-8 -*-
"""공용 tool-loop 그래프(planforge/llm/loops.py) 테스트 — nudge·재시도·소진·args 파싱.

메시지 조립 순서가 기존 수제 루프(derive·plan_revise·review·compact)와 동일함을
잠근다 — FakeLLM.calls 어설션이 각 사이트 테스트와 같은 형태다.
"""
import json

from fakes import FakeLLM, tool_call
from planforge.llm.loops import run_tool_loop

TOOL = {"type": "function", "function": {"name": "f", "parameters": {}}}
NUDGE = "f 도구를 호출하라. 도구 호출 외 출력 금지."


def _run(llm, validate, max_attempts=3, on_attempt=None):
    return run_tool_loop(llm, [TOOL], "f", max_attempts=max_attempts,
                         nudge_text=NUDGE, validate=validate,
                         on_attempt=on_attempt, messages=[
                             {"role": "system", "content": "sys"},
                             {"role": "user", "content": "hi"},
                         ])


# ---------------------------------------------------------------- 성공 경로

def test_nudge_then_success():
    """도구 누락 → assistant(content)+user(nudge) 추가 후 재호출 → 성공."""
    llm = FakeLLM([
        {"content": "도구를 못 찾겠습니다", "tool_calls": []},
        tool_call("f", {"x": 1}),
    ])
    final = _run(llm, lambda args: ("ok", args["x"] * 10))
    assert final["result"] == 10 and final["ok"] and final["attempts"] == 2
    # 조립 순서: assistant 행이 nudge user 행보다 먼저, nudge가 마지막
    assert llm.calls[1][-2]["role"] == "assistant"
    assert llm.calls[1][-2]["content"] == "도구를 못 찾겠습니다"
    assert llm.calls[1][-1]["role"] == "user"
    assert llm.calls[1][-1]["content"] == NUDGE
    assert llm.calls[1][0]["role"] == "system"  # 기존 messages 뒤에 붙는다


def test_nudge_content_empty_fallback():
    """LLM 응답에 content가 없으면 assistant 행 content는 '' (기존 사이트 동작)."""
    llm = FakeLLM([{"tool_calls": []}, tool_call("f", {"x": 1})])
    final = _run(llm, lambda args: ("ok", args))
    assert llm.calls[1][-2]["content"] == ""


def test_retry_feedback_pair_then_success():
    """검증 실패 → assistant.tool_calls + tool 피드백 쌍으로 재시도 → 성공."""
    llm = FakeLLM([tool_call("f", {"x": 1}), tool_call("f", {"x": 2})])

    def validate(args):
        if args["x"] == 1:
            return ("retry", "고쳐라")
        return ("ok", "통과")

    final = _run(llm, validate)
    assert final["result"] == "통과" and final["attempts"] == 2
    # 도구 결과 쌍 — id·args 직렬화·tool content가 프로토콜대로
    assistant = llm.calls[1][-2]
    assert assistant["role"] == "assistant" and assistant["content"] is None
    assert assistant["tool_calls"] == [{"id": "call_f", "type": "function",
                                        "function": {"name": "f",
                                                     "arguments": json.dumps({"x": 1}, ensure_ascii=False)}}]
    tool_msg = llm.calls[1][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "call_f"
    assert tool_msg["content"] == "고쳐라"


def test_retry_assistant_content_passthrough():
    """재시도 피드백의 assistant 행에 LLM 텍스트 응답이 그대로 실린다."""
    llm = FakeLLM([{"content": "설명", "tool_calls": [{"name": "f", "arguments": {"x": 1}}]},
                   tool_call("f", {"x": 2})])
    final = _run(llm, lambda args: ("retry", "고쳐라") if args["x"] == 1 else ("ok", 1))
    assert llm.calls[1][-2]["content"] == "설명"
    assert final["ok"]


def test_raw_string_args_parsed():
    """arguments가 JSON 문자열이면 파싱해 validate에 dict로 전달한다."""
    llm = FakeLLM([{"tool_calls": [{"name": "f", "arguments": json.dumps({"x": 7})}]}])
    seen = {}
    final = _run(llm, lambda args: (seen.update(args) or ("ok", args["x"])))
    assert seen == {"x": 7} and final["result"] == 7


# ---------------------------------------------------------------- 소진

def test_retry_exhaustion_returns_none():
    """검증 실패 지속 → max_attempts 소진 시 result None·ok False (caller가 오류로 변환)."""
    llm = FakeLLM([tool_call("f", {"x": n}) for n in (1, 2, 3)])
    final = _run(llm, lambda args: ("retry", "고쳐라"))
    assert final["result"] is None and not final["ok"] and final["attempts"] == 3
    assert len(llm.calls) == 3


def test_nudge_exhaustion_returns_none():
    """도구 누락 지속 → 소진 시 result None. nudge도 attempt를 소비한다."""
    llm = FakeLLM([{"content": "텍스트", "tool_calls": []} for _ in range(2)])
    final = _run(llm, lambda args: ("ok", None), max_attempts=2)
    assert final["result"] is None and not final["ok"] and final["attempts"] == 2
    assert len(llm.calls) == 2
    assert llm.calls[1][-1]["content"] == NUDGE  # 마지막 attempt에서도 nudge가 붙는다


def test_final_state_exposes_triage_fields():
    """소진 라벨링 판별용 final 상태 키 — derive.py가 도구 미호출 소진을 분류하는 데 읽는다
    (결정 16)."""
    # (a) 도구 미호출 소진 — tool_call None, 마지막 텍스트 응답 노출
    llm = FakeLLM([{"content": "텍스트", "tool_calls": []} for _ in range(2)])
    final = _run(llm, lambda args: ("ok", None), max_attempts=2)
    assert final["result"] is None
    assert final["tool_call"] is None
    assert final["resp_content"] == "텍스트"
    # (b) validate 소진 — 마지막 도구 호출 arguments가 그대로 남는다
    llm2 = FakeLLM([tool_call("f", {"x": 1}), tool_call("f", {"x": 2})])
    final2 = _run(llm2, lambda args: ("retry", "고쳐라"), max_attempts=2)
    assert final2["result"] is None
    assert final2["tool_call"] == {"name": "f", "arguments": {"x": 2}}


def test_messages_not_mutated_in_place():
    """caller의 messages 리스트를 복사해 쓴다 — 재시도 추가는 상태 안에서만."""
    llm = FakeLLM([tool_call("f", {"x": 1})])
    messages = [{"role": "user", "content": "hi"}]
    run_tool_loop(llm, [TOOL], "f", max_attempts=1, nudge_text=NUDGE,
                  validate=lambda args: ("ok", 1), messages=messages)
    assert messages == [{"role": "user", "content": "hi"}]


# ---------------------------------------------------------------- on_attempt 콜백

def test_on_attempt_called_before_each_chat_fn():
    """on_attempt가 chat_fn 호출 직전마다 (attempt, max_attempts)로 불린다."""
    llm = FakeLLM([tool_call("f", {"x": 1}), tool_call("f", {"x": 2})])
    seen = []

    def validate(args):
        if args["x"] == 1:
            return ("retry", "고쳐라")
        return ("ok", "통과")

    final = _run(llm, validate, on_attempt=lambda n, m: seen.append((n, m)))
    assert final["result"] == "통과"
    assert seen == [(1, 3), (2, 3)]


def test_on_attempt_none_by_default():
    """on_attempt 미지정(기본 None)에서 기존 동작 무변경 — 계약 회귀 확인."""
    llm = FakeLLM([tool_call("f", {"x": 1})])
    final = _run(llm, lambda args: ("ok", args["x"]))
    assert final["result"] == 1 and final["attempts"] == 1