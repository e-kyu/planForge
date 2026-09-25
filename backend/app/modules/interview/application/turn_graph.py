# -*- coding: utf-8 -*-
"""인터뷰 턴 루프의 LangGraph 오케스트레이션 (docs/architecture-decisions.md 편차 10).

턴 1건 = 그래프 1회 invoke. checkpointer 없음 — 세션 상태(phase·round_no·pending_*)
는 DB(interview_sessions)가 SSOT이고, 게이트(/answers·/facts/confirm·/key-messages)는
기존처럼 새 턴으로 재진입한다.

노드는 InterviewAgent의 도구 디스패치·이력 영속·이벤트 방출을 그대로 재사용해 DB 쓰기와
이벤트 순서를 기존 _loop와 동일하게 유지한다 (tests/test_interview_api.py가 고정).
프리셋(create_react_agent 등)을 쓰지 않는 이유: 도구 판정·게이트·검증·커밋은 서버 코드
권한이다 (설계 원칙 2).
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.tools import BLOCKING_TOOLS, INTERVIEW_TOOLS

from ..infrastructure.models import MessageKind, MessageRole
from ..domain.events import token_event
from .agent import MAX_TOOL_TURNS, PLAN_FIX_ATTEMPTS, TurnError

NUDGE_TEXT = ("도구(ask_questions·save_facts·confirm_key_messages·update_checklist·write_plan)를 "
              "호출해 진행하라. 도구 호출 외 출력 금지.")


class TurnState(TypedDict):
    """턴 루프 상태. messages는 OpenAI 프로토콜 dict — DB 히스토리 재구성과 동일 포맷."""
    messages: list[dict]
    text: str              # 마지막 LLM 응답 텍스트
    tool_calls: list[dict]
    nudges: int            # 도구 미호출 재호출 유도 횟수 (1회 한도)
    plan_fixes: int        # write_plan 검증 실패 횟수
    turns: int             # 지금까지의 LLM 호출 횟수 (MAX_TOOL_TURNS 한도)
    next: str              # dispatch_non_blocking → 라우팅 결정 (call_llm|dispatch_blocking)
    blocking_error: bool   # blocking 도구 결과가 ERROR: 피드백인지


def build_turn_graph(agent, events, max_turns: int = MAX_TOOL_TURNS,
                     plan_fix_attempts: int = PLAN_FIX_ATTEMPTS):
    """에이전트 1개에 바인딩된 턴 그래프를 컴파일한다."""

    def call_llm(state: TurnState) -> dict:
        text_parts: list[str] = []
        tool_calls: list[dict] = []
        for ev in agent.stream_fn(state["messages"], tools=INTERVIEW_TOOLS):
            if ev["type"] == "text":
                text_parts.append(ev["delta"])
                events.add(token_event(ev["delta"]))
            elif ev["type"] == "tool_call":
                tool_calls.append({"name": ev["name"], "arguments": ev["arguments"]})
        text = "".join(text_parts)
        if text.strip():
            agent._append(MessageRole.ASSISTANT, MessageKind.TEXT, content=text)
        return {"text": text, "tool_calls": tool_calls, "turns": state["turns"] + 1}

    def route_after_llm(state: TurnState) -> str:
        if state["tool_calls"]:
            return "dispatch_non_blocking"
        if state["text"].strip() and state["nudges"] == 0:
            return "nudge"
        raise TurnError("LLM이 도구 호출 없이 응답을 마쳤습니다")

    def nudge(state: TurnState) -> dict:
        # 스트리밍 폴백(D9): 도구 호출 없이 텍스트만 나온 턴 — 1회 재호출 유도
        if state["turns"] >= max_turns:
            raise TurnError(f"턴 내 도구 루프 한도({max_turns}) 초과")
        return {"messages": state["messages"] + [
            {"role": "assistant", "content": state["text"]},
            {"role": "user", "content": NUDGE_TEXT},
        ], "nudges": state["nudges"] + 1}

    def dispatch_non_blocking(state: TurnState) -> dict:
        messages = list(state["messages"])
        for tc in state["tool_calls"]:
            if tc["name"] in BLOCKING_TOOLS:
                continue
            result = agent._dispatch(tc, events)
            agent._persist_tool_exchange(tc, result)
            messages += agent._tool_messages(tc, result)
        if not any(tc["name"] in BLOCKING_TOOLS for tc in state["tool_calls"]):
            # 비차단 도구만 있으면 같은 턴에서 루프 지속 — 단, LLM 호출 한도 검사
            if state["turns"] >= max_turns:
                raise TurnError(f"턴 내 도구 루프 한도({max_turns}) 초과")
            return {"messages": messages, "next": "call_llm"}
        return {"messages": messages, "next": "dispatch_blocking"}

    def dispatch_blocking(state: TurnState) -> dict:
        tc = next(tc for tc in state["tool_calls"] if tc["name"] in BLOCKING_TOOLS)
        if tc["name"] == "write_plan" and state["plan_fixes"] >= plan_fix_attempts:
            raise TurnError("plan 검증 재시도 한도 초과")
        result = agent._dispatch(tc, events)
        agent._persist_tool_exchange(tc, result)
        error = isinstance(result, str) and result.startswith("ERROR:")
        plan_fixes = state["plan_fixes"] + (1 if error and tc["name"] == "write_plan" else 0)
        return {"messages": state["messages"] + agent._tool_messages(tc, result),
                "plan_fixes": plan_fixes, "blocking_error": error}

    def route_after_non_blocking(state: TurnState) -> str:
        return state["next"]

    def route_after_blocking(state: TurnState) -> str:
        if not state["blocking_error"]:
            return END  # blocking 도구로 턴 종료
        if state["turns"] >= max_turns:
            raise TurnError(f"턴 내 도구 루프 한도({max_turns}) 초과")
        return "call_llm"  # 검증 실패 피드백 → 재호출 유도

    graph = StateGraph(TurnState)
    graph.add_node("call_llm", call_llm)
    graph.add_node("nudge", nudge)
    graph.add_node("dispatch_non_blocking", dispatch_non_blocking)
    graph.add_node("dispatch_blocking", dispatch_blocking)
    graph.add_edge(START, "call_llm")
    graph.add_conditional_edges("call_llm", route_after_llm,
                                ["dispatch_non_blocking", "nudge"])
    graph.add_edge("nudge", "call_llm")
    graph.add_conditional_edges("dispatch_non_blocking", route_after_non_blocking,
                                ["call_llm", "dispatch_blocking"])
    graph.add_conditional_edges("dispatch_blocking", route_after_blocking, [END, "call_llm"])
    return graph.compile()