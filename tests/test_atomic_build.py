# -*- coding: utf-8 -*-
"""원자적 빌드 래퍼 테스트 — 채번 연속성(tmp 시딩)·크래시 안전을 잠근다 (D7)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.workspace import atomic_build, parse_build_filename
from fakes import correct_report_payload


def _work_report(ws: Path) -> Path:
    """실제 빌더가 먹는 work/report.json을 준비한다 (M1 파서로부터 파생물 생성은 Deriver 몫)."""
    work = ws / "work"
    work.mkdir(parents=True, exist_ok=True)
    p = work / "report.json"
    p.write_text(json.dumps(correct_report_payload(), ensure_ascii=False), encoding="utf-8")
    return p


def _builder(work_path: Path, fmts=("md",)):
    from reportagent.builders import build_doc

    def run(tmp: Path):
        for fmt in fmts:
            build_doc.build(str(work_path), fmt, str(tmp))

    return run


def test_atomic_build_first_version(tmp_path):
    p = _work_report(tmp_path)
    made = atomic_build(tmp_path, _builder(p))
    assert [f.name for f in made] == ["업무_자동화_도입_제안_v01.md"]
    assert made[0].is_file()
    assert not list((tmp_path / "output").glob(".tmp*"))  # tmp 정리


def test_atomic_build_version_continuity_with_seeded_output(tmp_path):
    """기존 v01이 있으면 tmp 시딩 덕에 v02가 나온다 — 빌더 코드 무변경으로 채번 연속성 유지 (원칙 5)."""
    p = _work_report(tmp_path)
    atomic_build(tmp_path, _builder(p))          # v01
    made = atomic_build(tmp_path, _builder(p))   # v02
    assert [f.name for f in made] == ["업무_자동화_도입_제안_v02.md"]
    names = sorted(f.name for f in (tmp_path / "output").iterdir())
    assert names == ["업무_자동화_도입_제안_v01.md", "업무_자동화_도입_제안_v02.md"]


def test_atomic_build_failure_leaves_output_untouched(tmp_path):
    p = _work_report(tmp_path)
    atomic_build(tmp_path, _builder(p))  # v01 존재

    def broken_builder(tmp: Path):
        raise RuntimeError("빌더 폭발")

    with pytest.raises(RuntimeError):
        atomic_build(tmp_path, broken_builder)
    # 기존 산출물 불변 + tmp 정리 + 신규 파일 없음
    names = sorted(f.name for f in (tmp_path / "output").iterdir())
    assert names == ["업무_자동화_도입_제안_v01.md"]


def test_parse_build_filename():
    assert parse_build_filename("업무_자동화_도입_제안_v02.md") == ("업무_자동화_도입_제안", 2, "md")
    assert parse_build_filename("report_v10.pptx") == ("report", 10, "pptx")
    assert parse_build_filename("draft.md") is None