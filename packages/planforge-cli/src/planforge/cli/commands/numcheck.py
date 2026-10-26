# -*- coding: utf-8 -*-
"""`planforge numcheck` — plan ↔ 파생물 수치 무결성 대조."""
from __future__ import annotations

from ...common.io import read_json
from ...numcheck import check_report, check_slides
from ...plan import parse_plan_file
from .parse import _filtered


def cmd_numcheck(args) -> int:
    plan = parse_plan_file(args.plan)
    doc, slides = _filtered(plan, args.doc)
    if not args.slides and not args.report:
        print("오류: --slides 또는 --report 중 하나는 필수입니다")
        return 2
    findings = []
    if args.slides:
        findings += check_slides(slides, plan.key_messages, read_json(args.slides))
        target = args.slides
    if args.report:
        findings += check_report(slides, plan.key_messages, read_json(args.report))
        target = args.report
    if not findings:
        print(f"OK: 수치 무결성 대조 통과 (plan [{doc}] ↔ {target})")
        return 0
    for f in findings:
        print(f)
    reds = sum(1 for f in findings if f.severity == "red")
    print(f"\n발견 {len(findings)}건 (🔴 {reds}건)"
          + (" — 파생물 재생성 필요" if reds else " — 경고만 있음, 진행 가능"))
    return 1 if reds else 0
