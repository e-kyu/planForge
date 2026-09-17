# -*- coding: utf-8 -*-
"""reportagent CLI (M1).

사용법 (backend/에서 실행):
  python -m reportagent parse <plan.md> [--doc 문서명]
  python -m reportagent numcheck <plan.md> --slides <slides.json> [--doc 문서명]
  python -m reportagent numcheck <plan.md> --report <report.json> [--doc 문서명]
  python -m reportagent build-ppt <slides.json> [output_dir]
  python -m reportagent build-doc <report.json> <md|html|docx> [output_dir]

LLM derive 단계는 M1 후반(provider 추상화 계층)에서 추가한다.
"""
from __future__ import annotations

import argparse
import sys

from .numcheck import check_report, check_slides
from .plan import filter_slides, parse_plan_file, validate_skeleton


def _filtered(plan, doc: str | None):
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


def cmd_numcheck(args) -> int:
    plan = parse_plan_file(args.plan)
    doc, slides = _filtered(plan, args.doc)
    if not args.slides and not args.report:
        print("오류: --slides 또는 --report 중 하나는 필수입니다")
        return 2
    findings = []
    if args.slides:
        import json

        findings += check_slides(slides, plan.key_messages, json.loads(_read(args.slides)))
        target = args.slides
    if args.report:
        import json

        findings += check_report(slides, plan.key_messages, json.loads(_read(args.report)))
        target = args.report
    if not findings:
        print(f"OK: 수치 무결성 대조 통과 (plan [{doc}] ↔ {target})")
        return 0
    for f in findings:
        print(f)
    reds = sum(1 for f in findings if f.severity == "red")
    print(f"\n발견 {len(findings)}건 (🔴 {reds}건) — 파생물 재생성 필요")
    return 1 if reds else 0


def _read(path: str) -> str:
    from pathlib import Path

    return Path(path).read_text(encoding="utf-8-sig")


def cmd_build_ppt(args) -> int:
    from .builders import build_ppt

    build_ppt.build(args.slides_json, args.output_dir)
    return 0


def cmd_build_doc(args) -> int:
    from .builders import build_doc

    build_doc.build(args.report_json, args.fmt, args.output_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="reportagent", description="report-agent 코어 엔진 (M1)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("parse", help="plan.md 파싱·필터·골격 검증")
    sp.add_argument("plan")
    sp.add_argument("--doc", help="대상 문서명 (기본: 첫 산출 문서)")
    sp.set_defaults(fn=cmd_parse)

    sn = sub.add_parser("numcheck", help="수치 무결성 대조")
    sn.add_argument("plan")
    sn.add_argument("--slides", help="slides.json 경로")
    sn.add_argument("--report", help="report.json 경로")
    sn.add_argument("--doc", help="대상 문서명 (기본: 첫 산출 문서)")
    sn.set_defaults(fn=cmd_numcheck)

    s1 = sub.add_parser("build-ppt", help="slides.json → PPTX (legacy 빌더 원형)")
    s1.add_argument("slides_json")
    s1.add_argument("output_dir", nargs="?", default="")
    s1.set_defaults(fn=cmd_build_ppt)

    s2 = sub.add_parser("build-doc", help="report.json → md|html|docx (legacy 빌더 원형)")
    s2.add_argument("report_json")
    s2.add_argument("fmt", choices=["md", "html", "docx"])
    s2.add_argument("output_dir", nargs="?", default="")
    s2.set_defaults(fn=cmd_build_doc)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())