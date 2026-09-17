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
import os
import sys
from pathlib import Path

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


def cmd_derive(args) -> int:
    from .derive import Deriver, UNCONFIRMED_MARK
    from .llm import get_provider, load_config

    config_path = (args.config or os.environ.get("REPORTAGENT_CONFIG")
                   or Path(__file__).resolve().parent / "config.json")
    if not Path(config_path).is_file():
        print(f"오류: LLM 설정 파일이 없습니다: {config_path}")
        print("backend/reportagent/config.example.json을 config.json으로 복사해 모델을 지정하거나,")
        print("환경변수 REPORTAGENT_CONFIG로 경로를 지정하세요.")
        return 2
    profiles = load_config(config_path)
    provider = get_provider(profiles["derive"])

    # (미확정) 수치 전제 확인 (make-ppt/make-doc 전제 절차 이식)
    plan = parse_plan_file(args.plan)
    doc_name = args.doc or plan.docs[0]
    slides = filter_slides(plan.slides, doc_name)
    validate_skeleton(slides)
    unconfirmed = [s.no for s in slides
                   if UNCONFIRMED_MARK in (s.source or "") or UNCONFIRMED_MARK in (s.message or "")]
    if unconfirmed and not args.allow_unconfirmed:
        print(f"(미확정) 표기가 남은 슬라이드: {unconfirmed} — 확정 수치로 채울지 확인이 필요합니다.")
        print("그대로 진행하려면 --allow-unconfirmed 옵션을 사용하세요.")
        return 2

    d = Deriver(provider.chat, args.workspace)
    res = d.derive(args.plan, args.kind, args.doc)
    print(f"OK: {res.work_path} (시도 {res.attempts}회, "
          + (f"슬라이드 {res.slides_count}개" if args.kind == "slides" else f"섹션 {res.sections_count}개") + ")")
    if res.unconfirmed:
        print(f"주의: (미확정) 표기 슬라이드 {res.unconfirmed} — 산출물에 그대로 유지됩니다")
    if args.no_build:
        return 0
    outs = d.build(args.kind, tuple(args.fmts) if args.fmts else ())
    for o in outs:
        print(f"산출물: {o}")
    return 0


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

    sd = sub.add_parser("derive", help="plan.md → 파생물 생성 (LLM 변환 + 빌드) — make-ppt/make-doc 이식")
    sd.add_argument("plan")
    sd.add_argument("--workspace", required=True, help="워크스페이스 디렉토리 (work/·output/ 생성)")
    sd.add_argument("--kind", choices=["slides", "report"], required=True)
    sd.add_argument("--doc", help="대상 문서명 (기본: 첫 산출 문서)")
    sd.add_argument("--fmts", nargs="*", choices=["md", "html", "docx"], help="report 빌드 포맷 (기본 3종 전부)")
    sd.add_argument("--no-build", action="store_true", help="work/*.json 생성까지만 수행")
    sd.add_argument("--allow-unconfirmed", action="store_true", help="(미확정) 표기를 그대로 진행")
    sd.add_argument("--config", help="LLM 설정 파일 경로 (기본: REPORTAGENT_CONFIG > backend/reportagent/config.json)")
    sd.set_defaults(fn=cmd_derive)

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