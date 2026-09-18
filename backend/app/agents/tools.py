# -*- coding: utf-8 -*-
"""인터뷰 에이전트 도구 스키마 + 서버측 검증.

도구는 FR-2 상태머신의 상태 전이 트리거다:
- blocking 도구(ask_questions·save_facts·confirm_key_messages·write_plan): 호출 시 턴 종료 + 게이트 전이
- update_checklist(비차단): 체크리스트 갱신 후 루프 지속
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------- OpenAI function 스키마

INTERVIEW_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "ask_questions",
            "description": ("다음 인터뷰 라운드의 질문을 제시한다 (라운드당 최대 4문항). "
                            "선택지는 상호배타적·실제 사례 기반으로 하고 근거를 설명에 포함한다. "
                            "서술형 주제는 allow_free=true."),
            "parameters": {
                "type": "object",
                "properties": {
                    "round_summary": {"type": "string",
                                      "description": "이번 라운드의 목표 한 줄 요약"},
                    "questions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "options": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "label": {"type": "string"},
                                            "description": {"type": "string"},
                                        },
                                        "required": ["label"],
                                    },
                                },
                                "allow_free": {"type": "boolean"},
                            },
                            "required": ["text"],
                        },
                    },
                },
                "required": ["questions"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_facts",
            "description": ("이번 라운드에서 확정된 팩트(3~5줄 요약)를 제시한다. "
                            "사용자 확인 게이트를 통과한 뒤에만 팩트 저장소에 적립된다. "
                            "이전 답변과 충돌하면 conflicts에 적고 조용히 덮지 않는다."),
            "parameters": {
                "type": "object",
                "properties": {
                    "facts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "source": {"type": "string",
                                           "description": "출처 (인터뷰 답변/소스 문서 등)"},
                            },
                            "required": ["content"],
                        },
                    },
                    "conflicts": {
                        "type": "array",
                        "items": {"type": "object",
                                  "properties": {"note": {"type": "string"}},
                                  "required": ["note"]},
                    },
                },
                "required": ["facts"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_key_messages",
            "description": ("라운드 2 종료 시점에 핵심 메시지 후보 정확히 3개를 제시해 승인을 받는다. "
                            "이후 라운드의 목표는 이 3개를 성립시킬 근거 수집이다."),
            "parameters": {
                "type": "object",
                "properties": {
                    "messages": {
                        "type": "array", "items": {"type": "string"},
                        "minItems": 3, "maxItems": 3,
                    },
                },
                "required": ["messages"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_checklist",
            "description": ("종료 판정 체크리스트를 갱신한다 (비차단 — 즉시 루프가 이어진다). "
                            "area는 공통|제안서|개발설계서 중 하나."),
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "area": {"type": "string"},
                                "text": {"type": "string"},
                                "done": {"type": "boolean"},
                            },
                            "required": ["id", "text", "done"],
                        },
                    },
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_plan",
            "description": ("인터뷰 결과를 plan.md 마크다운으로 작성한다 (정확히 3개의 핵심 메시지, "
                            "7종 유형 표기, 근거 없는 수치는 (미확정)). 서버가 포맷을 검증하고 "
                            "통과하면 plan 승인 게이트로 넘어간다."),
            "parameters": {
                "type": "object",
                "properties": {
                    "markdown": {"type": "string"},
                },
                "required": ["markdown"],
            },
        },
    },
]

BLOCKING_TOOLS = {"ask_questions", "save_facts", "confirm_key_messages", "write_plan"}

MAX_QUESTIONS = 4  # FR-2.3: 한 라운드 최대 4문항


class ToolError(ValueError):
    """도구 인자 검증 실패 — tool 결과로 LLM에 되돌려 재호출을 유도한다."""


def validate_tool_args(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """도구 인자 검증 → 정규화된 args 반환. 실패 시 ToolError."""
    if name == "ask_questions":
        qs = args.get("questions") or []
        if not qs:
            raise ToolError("questions가 비어 있습니다 — 최소 1문항 필요")
        if len(qs) > MAX_QUESTIONS:
            raise ToolError(f"라운드당 최대 {MAX_QUESTIONS}문항입니다 (현재 {len(qs)}개) — "
                            f"{MAX_QUESTIONS}개만 남기고 나머지는 다음 라운드로")
        return args
    if name == "save_facts":
        facts = args.get("facts") or []
        if not facts:
            raise ToolError("facts가 비어 있습니다 — 확정된 팩트가 없으면 save_facts를 호출하지 말 것")
        return args
    if name == "confirm_key_messages":
        msgs = args.get("messages") or []
        if len(msgs) != 3:
            raise ToolError(f"핵심 메시지는 정확히 3개여야 합니다 (현재 {len(msgs)}개)")
        return args
    if name == "update_checklist":
        return args
    if name == "write_plan":
        if not (args.get("markdown") or "").strip():
            raise ToolError("markdown이 비어 있습니다")
        return args
    raise ToolError(f"알 수 없는 도구: {name}")