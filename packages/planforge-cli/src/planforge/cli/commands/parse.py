# -*- coding: utf-8 -*-
"""`planforge parse` — plan.md 파싱·문서 필터·골격 검증."""
from __future__ import annotations

from ...plan import filter_slides, parse_plan_file, validate_skeleton


def _filtered(plan, doc: str | None):
    """대상 문서 필터 + 골격 검증 — parse·numcheck 공용."""
    doc = doc or plan.docs[0]
    slides = filter_slides(plan.slides, doc)
    validate_skeleton(slides)
    return doc, slides


def cmd_parse(args) -> int:
    plan = parse_plan_file(args.plan)
    print(f"제목: {plan.title}")
    print(f"산출 문서: {', '.join(plan.docs)}")
    print(f"핵심 메시지: {len(plan.key_messages)}개")
    for i, km in enumerate(plan.key_messages, 1):
        print(f"  {i}. {km}")
    doc, slides = _filtered(plan, args.doc)
    print(f"\n[{doc}] 필터 슬라이드 {len(slides)}개 (골격 검증 통과):")
    for s in slides:
        print(f"  {s.no}. [{s.type}] {s.title}" + (f"  ← 문서 태그 {s.docs}" if s.docs else ""))
    return 0
