# -*- coding: utf-8 -*-
"""팩트 압축 에이전트 (FR-6.1, legacy compact-log.md 이식 — 원문은 git 이력 참조).

interview-log가 비대해졌을 때 통합 + 아카이브 방식으로 압축한다. 역할 분리:
LLM은 같은 주제의 항목들을 묶어 '최종 확정값 하나만 활성으로 남기고 이전 값은
archive로'하는 **그룹 판단만** 한다. DB 상태 변경·미러 파일 기록·검증은
결정론 코드가 담당한다 (facts API).

제약 (legacy compact-log.md 주의 절 이식):
- 팩트 손실 금지 — archive된 항목도 status='archived'로 DB에 그대로 남는다.
- 수치·내용은 한 글자도 바꾸지 않는다 (통합·이동만) — LLM은 content를 재작성하지
  못하고 keep/archive 선택만 한다.
- (미확정) 항목은 archive하지 않는다 — 활성에 유지.
"""
from __future__ import annotations

from pathlib import Path

from planforge.llm.loops import run_tool_loop

PROMPTS_DIR = Path(__file__).parent / "prompts"

UNCONFIRMED = "(미확정)"

COMPACT_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "propose_compact",
            "description": ("팩트 압축(통합+아카이브) 그룹을 제안한다. 같은 주제가 여러 번 "
                            "기록된 경우 최종 확정값 하나만 keep으로, 나머지(대체된 이전 값)를 "
                            "archive_ids로 지정한다. 통합 대상이 없는 항목은 어떤 그룹에도 "
                            "넣지 않는다. 내용은 절대 수정하지 않는다."),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string",
                                "description": "압축 현황 총평 1~2문장 (항목 수·중복 후보)"},
                    "groups": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "topic": {"type": "string",
                                          "description": "통합 주제 (예: '4분기 목표 매출')"},
                                "keep_id": {"type": "integer",
                                            "description": "활성으로 남을 팩트 id — 최종 확정값"},
                                "archive_ids": {"type": "array", "items": {"type": "integer"},
                                                "description": "이 값으로 대체된 이전 팩트 id들"},
                                "reason": {"type": "string",
                                           "description": "판단 근거 1문장 (날짜·확정 순서 등)"},
                            },
                            "required": ["topic", "keep_id", "archive_ids"],
                        },
                    },
                },
                "required": ["summary", "groups"],
            },
        },
    },
]


def build_context(facts: list[dict]) -> str:
    """LLM 압축 판단 입력 — facts: [{id, date, content, source}] (활성 팩트)."""
    lines = [f"- #{f['id']} [{f.get('date')}] {f.get('content', '')}"
             f" (출처: {f.get('source', '')})" for f in facts]
    return "## 활성 팩트 (id 오름차순 — 뒤쪽이 더 최근)\n" + "\n".join(lines)


def run_llm_compact(chat_fn, facts: list[dict]) -> tuple[list[dict], str, bool]:
    """LLM 압축 그룹 제안 1회. 반환: (groups, summary, llm_ok).

    groups: [{topic, keep_id, archive_ids, reason}] — 검증·적용은 API의 결정론 코드가 한다.
    도구 누락 시 nudge — LangGraph tool 루프 (편차 11, planforge/llm/loops.py,
    max_attempts=2: 1회 + nudge 1회). 도구 호출 실패 시 압축 제안만 실패로 기록한다
    (팩트는 건드리지 않았으므로 무손실).
    """
    system = (PROMPTS_DIR / "compact.md").read_text(encoding="utf-8-sig")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": build_context(facts)},
    ]

    def validate(args: dict) -> tuple[str, object]:
        groups = args.get("groups") or []
        for g in groups:
            g.setdefault("topic", "")
            g.setdefault("archive_ids", [])
            g.setdefault("reason", "")
        return ("ok", (groups, args.get("summary", "")))

    final = run_tool_loop(chat_fn, COMPACT_TOOLS, "propose_compact", max_attempts=2,
                          nudge_text=("propose_compact 도구를 호출해 통합 그룹을 제안하라. "
                                      "통합 대상이 없으면 빈 groups 배열로. 도구 호출 외 출력 금지."),
                          validate=validate, messages=messages)
    if final["result"] is None:
        return ([], "", False)
    return (*final["result"], True)


# ---------------------------------------------------------------- 결정론 검증·적용 (게이트)

def clean_groups(groups: list[dict], facts) -> list[dict]:
    """LLM 제안을 결정론 검증·정화한다 — 존재하지 않는 id·(미확정) 항목 archive 금지."""
    by_id = {f.id: f for f in facts}
    cleaned: list[dict] = []
    for g in groups:
        keep = g.get("keep_id")
        if keep not in by_id:
            continue
        archives: list[int] = []
        for aid in sorted({a for a in g.get("archive_ids", []) if isinstance(a, int)}):
            f = by_id.get(aid)
            if f is None or aid == keep or UNCONFIRMED in f.content:
                continue  # (미확정) 항목은 활성 유지 (legacy 주의 절 — 결정론 강제)
            archives.append(aid)
        if archives:
            cleaned.append({"topic": str(g.get("topic", "")), "keep_id": keep,
                            "archive_ids": archives, "reason": str(g.get("reason", ""))})
    return cleaned


def fact_line(f, marker: str = "") -> str:
    """interview-log 항목 형식 — 날짜·출처 표기 형식은 legacy 규약 유지."""
    line = f"[{f.date.isoformat()}] {f.content} (출처: {f.source})"
    return f"{line} {marker}".strip() if marker else line


def select_archives(facts, groups) -> tuple[dict[int, object], list[str]]:
    """승인 그룹 → archive 대상 + 경고. keep 누락·(미확정) 항목은 제외한다."""
    by_id = {f.id: f for f in facts}
    warnings: list[str] = []
    to_archive: dict[int, object] = {}
    for g in groups:
        if g.keep_id not in by_id:
            warnings.append(f"그룹 '{g.topic}': keep #{g.keep_id}가 활성 팩트가 아닙니다 — 건너뜀")
            continue
        for aid in g.archive_ids:
            if aid == g.keep_id:
                continue
            f = by_id.get(aid)
            if f is None:
                continue
            if UNCONFIRMED in f.content:
                warnings.append(f"팩트 #{aid}는 (미확정) 항목이라 archive하지 않았습니다")
                continue
            to_archive[aid] = f
    return to_archive, warnings