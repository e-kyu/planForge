# -*- coding: utf-8 -*-
"""문서별 루프 워크스페이스 경로 헬퍼 (doc_ws_root · ensure_doc_ws) 테스트."""
from __future__ import annotations

import pytest

from app.shared.workspace import (
    DOC_WS_SUBDIRS,
    WorkspaceError,
    doc_ws_root,
    ensure_doc_ws,
)


def test_doc_layout_with_slug_returns_doc_subdir(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    assert doc_ws_root(ws, "proposal", doc_layout=True) == ws / "proposal"


def test_no_doc_layout_returns_root_even_with_slug(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    # doc_layout=False + doc_slug 조합 — 레거시 프로젝트의 문서 세션 허용 계약
    assert doc_ws_root(ws, "proposal", doc_layout=False) == ws


def test_none_slug_returns_root(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    assert doc_ws_root(ws, None, doc_layout=True) == ws


def test_empty_slug_returns_root(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    assert doc_ws_root(ws, "", doc_layout=True) == ws


def test_bad_slug_rejected_as_traversal(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    for bad in ("..", "has_underscore", "-leading", "한글"):
        with pytest.raises(WorkspaceError):
            doc_ws_root(ws, bad, doc_layout=True)


def test_ensure_doc_ws_creates_four_subdirs_idempotent(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    root = ensure_doc_ws(ws / "proposal")
    assert root == ws / "proposal"
    for sub in DOC_WS_SUBDIRS:
        assert (root / sub).is_dir(), sub
    # sources는 문서 간 공유 소스라 문서별 하위에 만들지 않는다
    assert not (root / "sources").exists()

    # 멱등 + 기존 파일 훼손 없음
    marker = root / "work" / "keep.txt"
    marker.write_text("x", encoding="utf-8")
    assert ensure_doc_ws(root) == root
    for sub in DOC_WS_SUBDIRS:
        assert (root / sub).is_dir(), sub
    assert marker.read_text(encoding="utf-8") == "x"