# -*- coding: utf-8 -*-
"""`python -m planforge` 진입점 — 호환 shim.

CLI 본문은 `planforge/cli/`로 분리됐다. 이 모듈은 기존 계약만 유지한다:
`from planforge import __main__ as m`에서 `m.argparse`·`m.cmd_*`가 module attribute로
보인다 (`tests/test_derive.py`가 `cmd_derive`를 직접 호출한다).
"""
from __future__ import annotations

import argparse  # legacy 재수출
from .cli.commands.build import cmd_build_doc, cmd_build_ppt
from .cli.commands.derive import cmd_derive
from .cli.commands.numcheck import cmd_numcheck
from .cli.commands.parse import cmd_parse
from .cli.main import build_parser, main

if __name__ == "__main__":
    raise SystemExit(main())
