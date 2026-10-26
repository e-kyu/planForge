# -*- coding: utf-8 -*-
"""`planforge build-ppt` · `build-doc` — legacy 빌더 원형 실행."""
from __future__ import annotations


def cmd_build_ppt(args) -> int:
    from ...builders import build_ppt

    build_ppt.build(args.slides_json, args.output_dir)
    return 0


def cmd_build_doc(args) -> int:
    from ...builders import build_doc

    build_doc.build(args.report_json, args.fmt, args.output_dir)
    return 0
