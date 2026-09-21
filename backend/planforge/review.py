# -*- coding: utf-8 -*-
"""검수 엔진 — 결정론 검수 부분 (FR-4.1, review-doc.md 이식).

LLM이 판단할 수 없는 기계적 대조를 담당한다:
- 문서 태그 검수: 태그 어휘·문서별 골격·목차 재채번 정합
- 팩트 대조: 활성 팩트의 수치가 plan에 반영됐는지 / (미확정)이 팩트로 해소 가능한지
- 수치 무결성·구조 대조는 numcheck가, 세대 대응성은 DB 오케스트레이터(워커)가 담당한다.

발견사항은 numcheck.Finding을 그대로 쓴다 (severity: red|yellow|white).
"""
from __future__ import annotations

from dataclasses import dataclass

from .numcheck import Finding, UNCONFIRMED, numeric_tokens
from .plan.filter import doc_names, filter_slides
from .plan.model import Plan, Slide
from .plan.parser import parse_toc_items

# ---------------------------------------------------------------- 문서 태그 검수 (review-doc.md §3)

def check_doc_tags(plan: Plan) -> list[Finding]:
    """문서 태그 어휘·문서별 골격·목차 재채번(01..NN)을 검수한다.

    파생물 생성 시점에 골격 검증을 통과했더라도, 검수 시점의 plan 세대와
    파생물이 어긋났을 수 있어 다시 판정한다 (미달은 중단이 아니라 발견사항).
    """
    out: list[Finding] = []
    docs = doc_names(plan)
    multi = len(docs) > 1

    for s in plan.slides:
        for d in s.docs:
            if d not in docs and d != "공통":
                out.append(Finding(
                    "doc-tag", "red", f"슬라이드 {s.no} ({s.type})",
                    f"문서 태그 '{d}'가 메타 '산출 문서'({', '.join(docs)})에 없습니다"))

    if multi:
        for d in docs:
            filtered = filter_slides(plan.slides, d)
            missing = [label for label, t in (
                ("표지", "cover"), ("목차", "toc"), ("마무리", "closing")) if
                not any(s.type == t for s in filtered)]
            if missing or not any(s.is_content() for s in filtered):
                if missing:
                    out.append(Finding(
                        "doc-skeleton", "red", f"문서 '{d}'",
                        "문서별 골격 미달 — 다음 슬라이드가 없습니다: " + ", ".join(missing)))
            # 목차 불릿 ↔ 실제 내용 슬라이드 정합 (재채번 01..NN, 누락·과다 참조 없음)
            out.extend(_check_toc(d, filtered))
    return out


def _check_toc(doc: str, filtered: list[Slide]) -> list[Finding]:
    """해당 문서의 목차 불릿이 태그 필터 결과(내용 슬라이드)와 일치하는지."""
    tocs = [s for s in filtered if s.type == "toc"]
    content = [s for s in filtered if s.is_content()]
    out: list[Finding] = []
    if not tocs:
        return out  # 골격 검수에서 이미 보고됨
    toc = tocs[0]
    items = parse_toc_items(toc.message or "")
    if len(items) != len(content):
        out.append(Finding(
            "doc-toc", "yellow", f"문서 '{doc}' 목차 (슬라이드 {toc.no})",
            f"목차 불릿 {len(items)}개 vs 내용 슬라이드 {len(content)}개 — "
            "누락·과다 참조가 있습니다"))
    labels = [it.label for it in items]
    expect = [f"{i + 1:02d}" for i in range(len(labels))]
    if labels != expect:
        out.append(Finding(
            "doc-toc", "yellow", f"문서 '{doc}' 목차 (슬라이드 {toc.no})",
            f"목차 라벨이 01..{len(labels):02d} 재채번이 아닙니다: {', '.join(labels)}"))
    return out


# ---------------------------------------------------------------- 팩트 대조 (review-doc.md §5, FR-4.4)

def check_facts(plan: Plan, facts: list[dict]) -> list[Finding]:
    """확립 팩트 ↔ plan 대조.

    - 팩트의 수치가 plan에 없으면 red (수치 유실 — plan 반영 누락).
    - plan의 (미확정) 항목과 팩트가 같은 수치를 담으면 yellow — (미확정) 해소 대상.
    facts: [{content, source, date}] — DB Fact 행의 dict 표현.
    """
    out: list[Finding] = []
    plan_tokens: set[str] = set()
    for s in plan.slides:
        plan_tokens.update(numeric_tokens(_slide_all_text(s)))
    for km in plan.key_messages:
        plan_tokens.update(numeric_tokens(km))

    for f in facts:
        content = f.get("content", "")
        f_tokens = set(numeric_tokens(content))
        missing = f_tokens - plan_tokens
        if missing:
            out.append(Finding(
                "fact-mismatch", "red", "확립 팩트 대조",
                f"팩트의 수치 {sorted(missing)}가 plan에 없습니다 — {content[:60]}"))
        # (미확정) 해소 제안: plan의 미확정 슬라이드와 같은 수치를 팩트가 갖고 있으면
        for s in plan.slides:
            if UNCONFIRMED not in (s.source or "") and UNCONFIRMED not in (s.message or ""):
                continue
            s_tokens = set(numeric_tokens(_slide_all_text(s)))
            if f_tokens & s_tokens:
                out.append(Finding(
                    "unconfirmed-resolvable", "yellow", f"슬라이드 {s.no} ({s.type})",
                    f"(미확정) 수치가 확립 팩트와 일치합니다 — 확인 후 plan에서 표기를 해소하세요: "
                    f"{f.get('content', '')[:50]}"))
                break
    return out


def _slide_all_text(s: Slide) -> str:
    """슬라이드 전체 텍스트 (근거/출처 포함 — 팩트 대조는 출처의 수치도 판단 대상)."""
    parts = [s.title, s.message, s.source or ""]
    for col in (s.left, s.right):
        if col is not None:
            parts.append(col.heading)
            parts.extend(f"{b.label} {b.body}" for b in col.bullets)
    if s.table is not None:
        parts.extend(s.table.headers)
        parts.extend(str(c) for row in s.table.rows for c in row)
        if s.table.note:
            parts.append(s.table.note)
    if s.chart is not None:
        parts.extend(s.chart.categories)
        parts.extend(str(v) for sr in s.chart.series for v in sr.values)
    parts.extend(f"{g.name} {', '.join(g.items)}" for g in s.arch)
    return " ".join(parts)