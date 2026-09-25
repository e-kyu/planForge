# -*- coding: utf-8 -*-
"""plan revise 에이전트 — 검수 발견사항을 plan에 반영 (FR-4.3).

역할 분리: 검수 에이전트(review 모듈)는 판단만 하고, 반영은 이 모듈이
서버 코드로 진행한다. LLM은 콘텐츠 변환(선택 발견사항을 반영한 plan 마크다운
생성)만 하고, 저장 여부는 결정론 검증(validate_plan_markdown)이 판정한다 —
통과 시에도 파생물이 아니라 새 DRAFT plan 세대로만 들어가며, 승인 게이트와
파생물 재생성은 기존 게이트를 그대로 경유한다 (SSOT, 원칙 2·5).

LLM/코드 역할 분리:
- LLM: 발견사항 반영한 plan 마크다운 생성 (write_plan 도구 1회).
- 코드(결정론): 포맷·골격 검증, 변경 없음 판정, 새 세대 채번·미러 기록.
"""
from __future__ import annotations

from pathlib import Path

from planforge.llm.loops import run_tool_loop
from planforge.plan import Plan as ParsedPlan
from planforge.plan import PlanError, filter_slides, parse_plan_text, validate_skeleton

from app.agents.tools import WRITE_PLAN_TOOL

PROMPTS_DIR = Path(__file__).parent / "prompts"
MAX_ATTEMPTS = 3
TOOL_NAME = "write_plan"


class PlanReviseError(ValueError):
    """plan 반영 실패 (LLM 미응답·도구 누락·포맷 검증 실패 지속)."""


def validate_plan_markdown(markdown: str) -> ParsedPlan:
    """plan 포맷 + 골격 검증 (원칙 8 — 미달 시 PlanError). presentation/api.py가 위임하는 단일 권위."""
    plan = parse_plan_text(markdown)
    if len(plan.key_messages) != 3:
        raise PlanError(f"핵심 메시지는 정확히 3개여야 합니다 (현재 {len(plan.key_messages)}개)")
    for doc in plan.docs:
        validate_skeleton(filter_slides(plan.slides, doc))
    return plan


def build_context(base_markdown: str, findings: list[dict], summary: str) -> str:
    """LLM revise 입력 컨텍스트 — 발견사항(제안 포함) 먼저, plan 전문을 기준으로."""
    parts = ["## 반영 대상 발견사항 (검수 결과)"]
    for i, f in enumerate(findings, 1):
        line = (f"{i}. [{f.get('severity', 'yellow')}/{f.get('code', '')}] "
                f"{f.get('where', '')}: {f.get('message', '')}")
        sug = f.get("suggestion")
        if sug:
            line += f"\n   - 제안(방향): {sug}"
        parts.append(line)
    parts.append(f"\n## 검수 총평\n{summary or '(없음)'}")
    parts.append("## plan.md 전문 (SSOT — 이 기준을 고쳐 전달)\n" + base_markdown)
    return "\n\n".join(parts)


def run_plan_revise(chat_fn, base_markdown: str, findings: list[dict],
                    summary: str = "") -> tuple[str, ParsedPlan]:
    """선택 발견사항을 반영한 plan 마크다운을 생성한다. 반환: (markdown, 파싱 결과).

    도구 누락 시 nudge, 포맷 검증 실패 시 도구 호출 결과 프로토콜로 피드백을
    되돌려 재시도 (최대 MAX_ATTEMPTS) — LangGraph tool 루프 (편차 11,
    planforge/llm/loops.py::run_tool_loop, derive.py의 재변환 루프와 동일 패턴).
    소진 시 PlanReviseError.
    """
    system = (PROMPTS_DIR / "plan_revise.md").read_text(encoding="utf-8-sig")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": build_context(base_markdown, findings, summary)},
    ]
    last_error: Exception | None = None

    def validate(args: dict) -> tuple[str, object]:
        nonlocal last_error
        md = (args.get("markdown") or "").strip()
        try:
            parsed = validate_plan_markdown(md)
        except PlanError as e:
            last_error = e
            return ("retry", "plan 포맷 검증 실패 — 아래 오류를 해소해 write_plan 도구를 다시 "
                             f"호출하라:\n{e}")
        return ("ok", (md, parsed))

    final = run_tool_loop(chat_fn, [WRITE_PLAN_TOOL], TOOL_NAME,
                          max_attempts=MAX_ATTEMPTS,
                          nudge_text=(f"{TOOL_NAME} 도구를 호출해 수정된 plan.md 마크다운 "
                                      "전체를 전달하라. 도구 호출 외 출력 금지."),
                          validate=validate, messages=messages)
    if final["result"] is None:
        raise PlanReviseError(
            f"plan 포맷 검증 실패가 {MAX_ATTEMPTS}회 재시도 후에도 해소되지 않았습니다: {last_error}")
    return final["result"]