# -*- coding: utf-8 -*-
"""CLI 진입점 분리 테스트 — 서브커맨드 stdout·exit code와 호환 shim 계약.

기존 테스트(test_derive.py)가 이미 고정한 문자열과 겹치지 않는 범위에서 핵심만 잠근다.
"""
import argparse
from pathlib import Path

import pytest

from planforge.cli.main import build_parser, main

FIX = Path(__file__).parent / "fixtures"
PLAN = FIX / "plan.sample.md"


def test_parse_success_prints_summary_and_exits_zero(capsys):
    assert main(["parse", str(PLAN)]) == 0
    out = capsys.readouterr().out
    assert "제목: 기획 (업무 자동화 — 제안·개발설계)" in out
    assert "산출 문서: 제안서, 개발설계서" in out
    assert "핵심 메시지: 3개" in out
    assert "[제안서] 필터 슬라이드" in out


def test_numcheck_red_exits_one(capsys):
    assert main(["numcheck", str(PLAN), "--slides", str(FIX / "slides.sample.json"),
                 "--doc", "제안서"]) == 1
    out = capsys.readouterr().out
    assert "[red]" in out
    assert "산출물을 다시 생성해 주세요" in out


def test_numcheck_missing_target_exits_two(capsys):
    assert main(["numcheck", str(PLAN)]) == 2
    assert "오류: --slides 또는 --report 중 하나는 필수입니다" in capsys.readouterr().out


def test_derive_missing_config_exits_two(tmp_path, capsys):
    rc = main(["derive", str(PLAN), "--workspace", str(tmp_path), "--kind", "slides",
               "--config", str(tmp_path / "none.json")])
    assert rc == 2
    assert "오류: LLM 설정 파일이 없습니다:" in capsys.readouterr().out


def test_build_ppt_command_builds_file(tmp_path, capsys):
    assert main(["build-ppt", str(FIX / "slides.sample.json"), str(tmp_path)]) == 0
    assert "OK:" in capsys.readouterr().out
    assert list(tmp_path.glob("*.pptx"))


def test_build_doc_command_builds_file(tmp_path, capsys):
    assert main(["build-doc", str(FIX / "report.sample.json"), "md", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "OK:" in out and "sections" in out
    assert list(tmp_path.glob("*.md"))


def test_help_exits_zero_without_error(capsys):
    with pytest.raises(SystemExit) as ei:
        main(["--help"])
    assert ei.value.code == 0
    assert "usage: planforge" in capsys.readouterr().out


def test_build_parser_sets_prog():
    assert build_parser().prog == "planforge"


def test_legacy_shim_exposes_argparse_and_commands():
    """`from planforge import __main__ as m` 계약 — test_derive.py가 cmd_derive를 직접 호출한다."""
    from planforge import __main__ as m

    assert m.argparse is argparse
    for name in ("cmd_parse", "cmd_numcheck", "cmd_derive", "cmd_build_ppt", "cmd_build_doc"):
        assert callable(getattr(m, name))
    assert callable(m.main)
