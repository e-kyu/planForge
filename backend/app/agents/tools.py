# -*- coding: utf-8 -*-
"""인터뷰 에이전트 도구 스키마 + 서버측 검증.

도구는 FR-2 상태머신의 상태 전이 트리거다:
- blocking 도구(ask_questions·save_facts·confirm_key_messages·write_plan): 호출 시 턴 종료 + 게이트 전이
- update_checklist(비차단): 체크리스트 갱신 후 루프 지속
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------- OpenAI function 스키마

WRITE_PLAN_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "write_plan",
        "description": ("plan.md 마크다운 전체를 전달한다 (정확히 3개의 핵심 메시지, "
                        "7종 유형 표기, 근거 없는 수치는 (미확정)). 서버가 포맷을 검증하고 "
                        "통과하면 다음 단계(승인 게이트)로 넘어간다."),
        "parameters": {
            "type": "object",
            "properties": {
                "markdown": {"type": "string"},
            },
            "required": ["markdown"],
        },
    },
}

INTERVIEW_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "ask_questions",
            "description": ("다음 인터뷰 라운드의 질문을 제시한다 (라운드당 최대 4문항). "
                            "각 문항은 options 2개 이상 또는 allow_free=true 중 하나를 "
                            "반드시 갖는다 (둘 다 있어도 된다. 둘 다 없으면 서버가 거부한다). "
                            "선택지는 상호배타적·실제 사례 기반으로 하고 근거를 설명에 포함한다."),
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
                                    "minItems": 2,
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
                                "suggestions": {
                                    "type": "array",
                                    "maxItems": 3,
                                    "items": {"type": "string"},
                                    "description": ("추천 후보 답변 (최대 3개, 한 줄 문장). "
                                                    "소스·확립 팩트에서 도출한 것만 담는다. "
                                                    "추측이면 (미확정)을 문장에 포함한다."),
                                },
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
    WRITE_PLAN_TOOL,
]

BLOCKING_TOOLS = {"ask_questions", "save_facts", "confirm_key_messages", "write_plan"}

MAX_QUESTIONS = 4  # FR-2.3: 한 라운드 최대 4문항

MAX_SUGGESTIONS = 3  # 문항당 추천 후보 상한 (답변 카드의 추천 칩)

SUGGESTION_MAX_LEN = 120  # 추천 후보 한 줄 길이 상한

PROSE_OPTION_THRESHOLD = 2  # 본문에서 옵션 유사 줄이 이 수 이상이면 "선택지 나열"로 판정

# 질문 본문 안의 선택지 나열 탐지 — 라인 선두 마커. `예시:`(예 뒤 글자가 시)·한 줄
# 인라인 나열("예: A/B")은 줄 수가 임계 미달이라 통과한다 (거짓 양성 관리 — 완화 시
# 불릿 arm만 제거하는 한 줄 변경).
_PROSE_OPTION_LINE = re.compile(
    r"(?:예\s*[):]|보기\s*[):]|선택지\s*[:]|답안?\s*[:)]"      # 예: 예) 보기: 답: 답안:
    r"|\d{1,2}\s*[).]"                                          # 1. 2) 12.
    r"|[①-⑳]"                                                  # ① ② …
    r"|[가나다라마바사아자차]\s*[).]"                           # 가) 나) 다.
    r"|\(\s*(?:\d{1,2}|[가나다라마바사아자차]|[A-J])\s*\)"      # (1) (가) (A)
    r"|[*•·]\s|-\s)")                                           # 불릿 (뒤 공백 필수 — 하이픈 결합어 회피)


class ToolError(ValueError):
    """도구 인자 검증 실패 — tool 결과로 LLM에 되돌려 재호출을 유도한다."""


def _prose_option_lines(text: str) -> list[str]:
    """질문 본문에서 선택지 나열로 보이는 줄을 반환 (임계 판정은 validate_tool_args)."""
    return [ln.strip() for ln in re.split(r"\n|\\n", (text or ""))
            if _PROSE_OPTION_LINE.match(ln.strip())]


def validate_tool_args(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """도구 인자 검증 → 정규화된 args 반환. 실패 시 ToolError."""
    if not isinstance(args, dict):
        # 도구 인자는 항상 JSON object — list/str 등이면 AttributeError(세션 FAILED
        # 전파) 대신 재시도 피드백으로 되돌린다
        raise ToolError(f"도구 인자는 JSON object여야 합니다 (현재 {type(args).__name__})")
    if name == "ask_questions":
        qs = args.get("questions") or []
        if not qs:
            raise ToolError("questions가 비어 있습니다 — 최소 1문항 필요")
        if len(qs) > MAX_QUESTIONS:
            raise ToolError(f"라운드당 최대 {MAX_QUESTIONS}문항입니다 (현재 {len(qs)}개) — "
                            f"{MAX_QUESTIONS}개만 남기고 나머지는 다음 라운드로")
        # 문항별 선택지 계약: options 2개 이상 또는 allow_free=true (둘 다 없으면 거부)
        prose_bad: list[tuple[int, list[str]]] = []
        for i, q in enumerate(qs, 1):
            if not isinstance(q, dict):
                raise ToolError(f"문항 {i}: 문항은 object여야 합니다")
            prose_bad.append((i, _prose_option_lines(q.get("text") or "")))
            # 추천 후보 칩 계약(선택 필드 — 없는 문항 통과). options 분기의 continue가
            # 이 검증을 우회하지 않도록 options 처리 앞에서 검증한다.
            sugs = q.get("suggestions")
            if sugs is not None:
                if not isinstance(sugs, list):
                    raise ToolError(f"문항 {i}: suggestions는 문자열 배열이어야 합니다 "
                                    f"(현재 {type(sugs).__name__}) — 추천 후보 문장들의 배열로")
                for k, s in enumerate(sugs, 1):
                    if not isinstance(s, str):
                        raise ToolError(f"문항 {i} 추천 후보 {k}: 후보는 문자열이어야 합니다")
                    if not s.strip():
                        raise ToolError(f"문항 {i} 추천 후보 {k}: 후보가 비어 있습니다 — "
                                        f"빈 후보를 제거하거나 문장을 채워라")
                    if "\n" in s or "\\n" in s:
                        raise ToolError(f"문항 {i} 추천 후보 {k}: 추천 후보는 한 줄 문장이다 — "
                                        f'"{s[:60]}…" (개행 제거 후 칩 한 줄로 요약)')
                if len(sugs) > MAX_SUGGESTIONS:
                    raise ToolError(f"문항 {i}: 추천 후보는 최대 {MAX_SUGGESTIONS}개다 "
                                    f"(현재 {len(sugs)}개) — 가장 설득력 있는 "
                                    f"{MAX_SUGGESTIONS}개만 남겨라")
                if any(len(s.strip()) > SUGGESTION_MAX_LEN for s in sugs):
                    long_one = next(s for s in sugs if len(s.strip()) > SUGGESTION_MAX_LEN)
                    raise ToolError(f"문항 {i}: 추천 후보는 {SUGGESTION_MAX_LEN}자 이내 한 줄이다 "
                                    f'("{long_one.strip()[:30]}…") — 근거 요약으로 짧게')
                q["suggestions"] = [s.strip() for s in sugs]
            opts = q.get("options") or []
            if not opts:
                if q.get("allow_free") is not True:
                    raise ToolError(f"문항 {i}: 선택지가 없습니다 — 객관형이면 options를 "
                                    f"2개(라벨+설명) 이상 채우고, 서술형 주제면 options 없이 "
                                    f"allow_free=true를 명시하라")
                continue
            if len(opts) < 2:
                raise ToolError(f"문항 {i}: 선택지는 2개 이상이어야 합니다 (현재 {len(opts)}개) — "
                                f"서술형 주제면 options를 빼고 allow_free=true로")
            for j, o in enumerate(opts, 1):
                if not isinstance(o, dict):
                    raise ToolError(f"문항 {i} 옵션 {j}: 옵션은 object여야 합니다")
                label = o.get("label")
                if not isinstance(label, str) or not label.strip():
                    raise ToolError(f"문항 {i} 옵션 {j}: label이 비어 있습니다")
                o["label"] = label.strip()
                desc = o.get("description")
                if desc is not None and not isinstance(desc, str):
                    raise ToolError(f"문항 {i} 옵션 {j}: description은 문자열이어야 합니다")
        # 본문 서술형 선택지 나열 — options 유무와 무관한 계약 위반이다(선택지는 options
        # 배열로만 전달). 위반 문항을 집계해 한 번에 알려 재시도 1회로 수렴시킨다.
        bad = [(i, lines) for i, lines in prose_bad if len(lines) >= PROSE_OPTION_THRESHOLD]
        if bad:
            names = "; ".join(f'문항 {i}("{lines[0][:30]}…")' for i, lines in bad)
            raise ToolError(
                f"질문 본문에 선택지 나열이 있습니다 — {names}. 선택지는 본문 텍스트에서 빼고 "
                f"options 배열({{label, description}})로 옮겨라. 서술형 주제면 나열을 모두 "
                f"제거하고 allow_free=true만 남긴다. 문항당 1개 주제로 나눌 것")
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