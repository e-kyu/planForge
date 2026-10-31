# -*- coding: utf-8 -*-
"""planforge CLI 진입점 — 서브커맨드 등록과 디스패치.

사용법 (backend/에서 실행):
  python -m planforge parse <plan.md> [--doc 문서명]
  python -m planforge numcheck <plan.md> --slides <slides.json> [--doc 문서명]
  python -m planforge numcheck <plan.md> --report <report.json> [--doc 문서명]
  python -m planforge build-ppt <slides.json> [output_dir]
  python -m planforge build-doc <report.json> <md|html|docx> [output_dir]
  python -m planforge derive <plan.md> --workspace <dir> --kind slides|report ...
"""
from __future__ import annotations

import argparse
import sys

from .commands.build import cmd_build_doc, cmd_build_ppt
from .commands.derive import cmd_derive
from .commands.numcheck import cmd_numcheck
from .commands.parse import cmd_parse


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="planforge", description="PlanForge 코어 엔진 (M1)")
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

    sd = sub.add_parser("derive", help="plan.md → 산출물 생성 (LLM 변환 + 빌드) — make-ppt/make-doc 이식")
    sd.add_argument("plan")
    sd.add_argument("--workspace", required=True, help="워크스페이스 디렉토리 (work/·output/ 생성)")
    sd.add_argument("--kind", choices=["slides", "report"], required=True)
    sd.add_argument("--doc", help="대상 문서명 (기본: 첫 산출 문서)")
    sd.add_argument("--fmts", nargs="*", choices=["md", "html", "docx"], help="report 빌드 포맷 (기본 3종 전부)")
    sd.add_argument("--no-build", action="store_true", help="work/*.json 생성까지만 수행")
    sd.add_argument("--allow-unconfirmed", action="store_true", help="(미확정) 표기를 그대로 진행")
    sd.add_argument("--config", help="LLM 설정 파일 경로 (기본: PLANFORGE_CONFIG > backend/planforge/config.json)")
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

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
