# -*- coding: utf-8 -*-
"""LLM 도구 루프의 LangGraph 오케스트레이션 (docs/architecture-decisions.md 편차 11).

derive(스키마·numcheck 재시도)·plan_revise(포맷 재시도)·review·compact(nudge)가
공유하는 단일 패턴 — "chat_fn 호출 → 도구 누락이면 nudge / 검증 실패면 tool 피드백
쌍으로 재시도 / 통과면 결과" — 를 StateGraph 하나로 표준화한다.

그래프는 제어 흐름만 표준화한다. 판정·피드백 문구는 caller가 주는 validate 클로저
(결정론 코드)가 담당한다 — LLM/코드 역할 분리(설계 원칙 2), 프리셋 에이전트 미채택.

계약: 루프 1건 = 그래프 1회 invoke, checkpointer 없음. messages는 OpenAI 프로토콜
dict(테스트 fake의 어설션·호출 사이트 포맷 유지). attempts = 총 chat_fn 호출 횟수 —
도구 누락 nudge도 1 attempt를 소비한다(기존 4곳 모두 동일). 도구 결과 피드백은
assistant.tool_calls → tool 쌍으로 되돌린다 — tool 응답 없이 user 피드백만 붙이면
OpenAI 호환 릴레이가 요청을 처리하지 못한다(ollama cloud 사고, derive.py 주석 이식).
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

# validate 프로토콜: args(dict) → ("ok", value) | ("retry", feedback_text)
ValidateFn = Callable[[dict], tuple[str, Any]]


class ToolLoopState(TypedDict):
    """tool 루프 상태. messages는 OpenAI 프로토콜 dict — 기존 루프와 동일 포맷."""
    messages: list[dict]
    resp_content: str      # 마지막 LLM 텍스트 응답 (재시도 피드백 assistant 행 원료)
    tool_call: dict | None # 마지막 LLM 응답의 대상 도구 호출 {"name", "arguments"}
    attempts: int          # 지금까지의 chat_fn 호출 횟수 (nudge 포함 — max_attempts 캡)
    ok: bool               # validate 통과 여부
    result: Any | None     # validate 통과 결과 — 소진 시 None


def build_tool_loop(chat_fn, tools, tool_name: str, *, max_attempts: int,
                    nudge_text: str, validate: ValidateFn):
    """chat_fn 계약의 도구 루프 1건을 컴파일한다. 소진 시 result=None·ok=False로 END —
    caller가 도메인 오류(DeriveError 등)나 ok=False로 변환한다."""

    def call_llm(state: ToolLoopState) -> dict:
        # 진행 관측용 로그 — attempt별 소요 시간과 컨텍스트 크기. 재시도마다 이전 응답의
        # 전체 JSON이 messages에 누적되므로 컨텍스트가 커지는 것도 여기서 보인다.
        t0 = time.monotonic()
        resp = chat_fn(state["messages"], tools=tools)
        elapsed = time.monotonic() - t0
        ctx_chars = sum(len(json.dumps(m, ensure_ascii=False)) for m in state["messages"])
        print(f"[tool-loop] attempt {state['attempts'] + 1}/{max_attempts} chat_fn 완료 "
              f"({elapsed:.0f}s, 컨텍스트 {ctx_chars:,}자)", flush=True)
        call = next((tc for tc in resp.get("tool_calls", []) if tc["name"] == tool_name),
                    None)
        if call is None:
            # 도구 누락 — 기존 사이트들과 동일 순서: assistant(content) → user(nudge)
            return {"messages": state["messages"] + [
                        {"role": "assistant", "content": resp.get("content") or ""},
                        {"role": "user", "content": nudge_text},
                    ],
                    "resp_content": resp.get("content") or "",
                    "tool_call": None, "attempts": state["attempts"] + 1}
        return {"resp_content": resp.get("content") or "", "tool_call": call,
                "attempts": state["attempts"] + 1}

    def route_after_call(state: ToolLoopState) -> str:
        if state["tool_call"]:
            return "validate"
        if state["attempts"] >= max_attempts:
            return END  # 소진 — caller가 result None으로 판정
        return "call_llm"

    def validate_node(state: ToolLoopState) -> dict:
        args = state["tool_call"]["arguments"]
        if isinstance(args, str):
            args = json.loads(args)  # 기존 사이트들과 동일 — 비보호 (예외 전파)
        outcome, value = validate(args)
        if outcome == "ok":
            return {"ok": True, "result": value}
        # 재시도 — assistant.tool_calls → tool 결과 쌍 (프로토콜 계약, 위 모듈 docstring)
        print(f"[tool-loop] 검증 실패 — 재시도 (attempts {state['attempts']}/{max_attempts})",
              flush=True)
        args_json = json.dumps(args, ensure_ascii=False)
        return {"messages": state["messages"] + [
                    {"role": "assistant", "content": state["resp_content"] or None,
                     "tool_calls": [{"id": f"call_{tool_name}", "type": "function",
                                     "function": {"name": tool_name,
                                                  "arguments": args_json}}]},
                    {"role": "tool", "tool_call_id": f"call_{tool_name}",
                     "content": value},
                ]}

    def route_after_validate(state: ToolLoopState) -> str:
        if state["ok"] or state["attempts"] >= max_attempts:
            return END
        return "call_llm"

    graph = StateGraph(ToolLoopState)
    graph.add_node("call_llm", call_llm)
    graph.add_node("validate", validate_node)
    graph.add_edge(START, "call_llm")
    graph.add_conditional_edges("call_llm", route_after_call, ["validate", "call_llm", END])
    graph.add_conditional_edges("validate", route_after_validate, ["call_llm", END])
    return graph.compile()


def run_tool_loop(chat_fn, tools, tool_name: str, *, max_attempts: int,
                  nudge_text: str, validate: ValidateFn,
                  messages: list[dict]) -> dict:
    """tool 루프 1건 실행 — 소진 여부 판정에 쓸 최종 상태(result·attempts·ok)를 반환."""
    graph = build_tool_loop(chat_fn, tools, tool_name, max_attempts=max_attempts,
                            nudge_text=nudge_text, validate=validate)
    return graph.invoke(
        {"messages": list(messages), "resp_content": "", "tool_call": None,
         "attempts": 0, "ok": False, "result": None},
        {"recursion_limit": max_attempts * 3 + 4},
    )