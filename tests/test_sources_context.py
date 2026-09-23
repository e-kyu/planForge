# -*- coding: utf-8 -*-
"""read_sources_context 주입 절단 상한 테스트 (파일별·전체 상한, 절단 마커)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.workspace import read_sources_context


def _write(d: Path, name: str, text: str) -> None:
    (d / name).write_text(text, encoding="utf-8")


def test_small_files_injected_whole(tmp_path):
    d = tmp_path / "global"
    d.mkdir()
    _write(d, "a.md", "본문 A")
    _write(d, "b.md", "본문 B")
    ctx = read_sources_context([d])
    assert ctx == "### 소스: a.md\n본문 A\n\n### 소스: b.md\n본문 B"
    assert "절단" not in ctx


def test_file_cap_truncates_with_marker(tmp_path):
    _write(tmp_path, "big.md", "가" * 30)
    _write(tmp_path, "small.md", "나" * 5)
    ctx = read_sources_context([tmp_path], max_chars=10, total_chars=100)
    assert "### 소스: big.md\n" + "가" * 10 + "\n...(절단: 주입 상한 10자 초과)" in ctx
    assert "나" * 5 in ctx  # 예산이 남아 다음 파일은 온전 주입


def test_total_budget_exhausted_lists_skipped(tmp_path):
    _write(tmp_path, "a.md", "가" * 60)
    _write(tmp_path, "b.md", "나" * 30)
    _write(tmp_path, "c.md", "다" * 10)
    ctx = read_sources_context([tmp_path], max_chars=100, total_chars=70)
    assert "### 소스: a.md\n" + "가" * 60 in ctx          # 온전 → 잔여 10자
    assert "### 소스: b.md\n" + "나" * 10 in ctx          # 잔여 예산으로 절단
    assert "다" not in ctx                                # 예산 소진
    assert "(전체 상한 도달로 미주입: c.md)" in ctx


def test_merge_across_dirs_in_order(tmp_path):
    g = tmp_path / "global"
    p = tmp_path / "project"
    g.mkdir()
    p.mkdir()
    _write(g, "baseline.md", "글로벌")
    _write(p, "요구사항.md", "프로젝트")
    ctx = read_sources_context([g, p])
    assert ctx.index("### 소스: baseline.md") < ctx.index("### 소스: 요구사항.md")


def test_whitelist_and_unreadable_skipped(tmp_path):
    _write(tmp_path, "doc.md", "마크다운")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / "cp949.txt").write_bytes("\xb1\xdb\xc0\xce".encode("latin-1"))
    (tmp_path / "noext").write_text("확장자없음", encoding="utf-8")
    assert read_sources_context([tmp_path]) == "### 소스: doc.md\n마크다운"


def test_missing_dir_ignored(tmp_path):
    assert read_sources_context([tmp_path / "없는디렉토리"]) == ""


def test_default_baseline_doc_injected_whole():
    """글로벌 베이스라인 문서가 기본 상한에서 절단 없이 온전 주입되는지 회귀 확인."""
    doc_dir = Path(__file__).resolve().parents[1] / "sources"
    doc = doc_dir / "default_architecture_guidelines.md"
    if not doc.is_file():
        pytest.skip("글로벌 베이스라인 문서가 없는 환경")
    text = doc.read_text(encoding="utf-8-sig")
    ctx = read_sources_context([doc_dir])
    assert "절단" not in ctx
    assert text[-50:] in ctx  # 문서 끝(제약·비목표)까지 온전