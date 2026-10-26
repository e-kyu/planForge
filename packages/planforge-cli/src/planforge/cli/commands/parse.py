# -*- coding: utf-8 -*-
"""`planforge parse` — plan.md 파싱·문서 필터·골격 검증."""
from __future__ import annotations

from ...plan.loader import load_plan_for_doc


def cmd_parse(args) -> int:
    prepared = load_plan_for_doc(args.plan, args.doc)
    plan = prepared.plan
    print(f"제목: {plan.title}")
    print(f"산출 문서: {', '.join(plan.docs)}")
    print(f"핵심 메시지: {len(plan.key_messages)}개")
    for i, km in enumerate(plan.key_messages, 1):
        print(f"  {i}. {km}")
    print(f"\n[{prepared.doc}] 필터 슬라이드 {len(prepared.slides)}개 (골격 검증 통과):")
    for s in prepared.slides:
        print(f"  {s.no}. [{s.type}] {s.title}" + (f"  ← 문서 태그 {s.docs}" if s.docs else ""))
    return 0
