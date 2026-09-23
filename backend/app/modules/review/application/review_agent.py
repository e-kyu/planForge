# -*- coding: utf-8 -*-
"""검수 에이전트 — LLM 내용 검수 부분 (FR-4, review-doc.md 이식).

결정론 검수(planforge/review.py·numcheck·run_review의 세대 대응)가 못 보는
내용 판단(주장 강도 왜곡·창작·팩트 불일치·문체)을 LLM에 위임한다.

역할 분리: LLM은 판단만 한다 — plan 수정·팩트 적립·재생성은 사용자 승인 후
서버 코드가 진행한다 (FR-4.3/4.4). 발견사항은 report_findings 도구로 1회 보고.
"""
from __future__ import annotations

import json
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"

MAX_FINDINGS = 40  # 폭주 방지 — 이 이상은 어차피 한 문장 요약으로 볼 수 없다

REVIEW_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "report_findings",
            "description": ("검수 발견사항을 보고한다. 기계적 검증(구조·수치·세대)은 이미 "
                            "서버가 했으므로 되풀이하지 않는다. 문제가 없으면 빈 배열."),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string",
                                "description": "검수 총평 1~2문장"},
                    "findings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "severity": {"type": "string",
                                             "enum": ["red", "yellow", "white"],
                                             "description": "red=사실 오류·수치 불일치, yellow=표현·구조, white=선택"},
                                "code": {"type": "string",
                                         "description": ("claim-distortion|fabrication|fact-mismatch|"
                                                         "fact-missing|unconfirmed-tone|style|typo|"
                                                         "structure-suggest")},
                                "where": {"type": "string",
                                          "description": "위치 (예: '슬라이드 3 (표)', 'report.json 섹션 2')"},
                                "message": {"type": "string",
                                            "description": "문제를 한 문장으로"},
                                "suggestion": {"type": "string",
                                               "description": "plan.md 관점의 수정 방향 (직접 고친 문장 아님)"},
                            },
                            "required": ["severity", "code", "where", "message"],
                        },
                    },
                },
                "required": ["findings"],
            },
        },
    },
]


def build_context(plan_markdown: str, derivative_docs: list[dict], facts: list[dict]) -> str:
    """LLM 검수 입력 컨텍스트. derivative_docs: [{doc, kind, json}] — 검수 대상 파생물."""
    parts = ["## plan 전문 (SSOT — 기준)\n", plan_markdown]
    for d in derivative_docs:
        doc_text = json.dumps(d["json"], ensure_ascii=False, indent=1)
        if len(doc_text) > 40000:
            doc_text = doc_text[:40000] + "\n…(잘림)"
        parts.append(f"\n## 파생물: {d['doc']} ({d['kind']})\n```json\n{doc_text}\n```")
    if facts:
        fact_lines = [f"- [{f.get('date')}] {f.get('content', '')} (출처: {f.get('source', '')})"
                      for f in facts]
        parts.append("\n## 확립 팩트 (interview-log)\n" + "\n".join(fact_lines))
    else:
        parts.append("\n## 확립 팩트\n(활성 팩트 없음)")
    return "\n".join(parts)


def run_llm_review(chat_fn, plan_markdown: str, derivative_docs: list[dict],
                   facts: list[dict]) -> tuple[list[dict], str, bool]:
    """LLM 내용 검수 1회. 반환: (findings, summary, llm_ok).

    도구 호출 실패 시 내용 검수만 실패로 기록하고 결정론 검수 결과는 보존한다
    (검수 전체가 실패하면 발견사항이 통째로 사라진다).
    """
    system = (PROMPTS_DIR / "review.md").read_text(encoding="utf-8-sig")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": build_context(plan_markdown, derivative_docs, facts)},
    ]
    for attempt in range(2):  # 1회 + 도구 누락 시 nudge 1회
        resp = chat_fn(messages, tools=REVIEW_TOOLS)
        calls = [tc for tc in resp.get("tool_calls", []) if tc["name"] == "report_findings"]
        if calls:
            args = calls[0]["arguments"]
            if isinstance(args, str):
                args = json.loads(args)
            findings = args.get("findings") or []
            for f in findings[:MAX_FINDINGS]:
                f.setdefault("severity", "yellow")
                if f["severity"] not in ("red", "yellow", "white"):
                    f["severity"] = "yellow"
                f.setdefault("code", "structure-suggest")
                f.setdefault("where", "파생물")
                f.setdefault("message", "")
            return (findings[:MAX_FINDINGS], args.get("summary", ""), True)
        messages = messages + [
            {"role": "assistant", "content": resp.get("content") or ""},
            {"role": "user", "content":
             "report_findings 도구를 호출해 발견사항을 보고하라. 도구 호출 외 출력 금지."},
        ]
    return ([], "", False)