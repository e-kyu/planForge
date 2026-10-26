# -*- coding: utf-8 -*-
"""문서별 루프 워크스페이스 경로 헬퍼 (doc_ws_root · ensure_doc_ws · resolve_workspace_root) 테스트."""
from __future__ import annotations

import pytest

from _helpers import make_project, make_session
from app.modules.docloops.facade import delete_project_data, resolve_workspace_root
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


# ---------------------------------------------------------------- resolve_workspace_root (docloops facade)

def test_resolve_workspace_root_legacy_returns_project_root(client, tmp_path):
    """doc_loops 행이 없는 레거시 프로젝트 — doc_slug가 있어도 루트 그대로."""
    pid = make_project(client, "wsrootlegacy")
    with make_session(client) as db:
        delete_project_data(db, pid)
        db.commit()
    ws = tmp_path / "proj"
    with make_session(client) as db:
        assert resolve_workspace_root(db, pid, ws, "proposal") == ws
        assert resolve_workspace_root(db, pid, ws, None) == ws


def test_resolve_workspace_root_doc_layout_returns_doc_subdir(client, tmp_path):
    """행이 있는 프로젝트 — ws/{doc_slug}. ensure 기본 False는 지연 생성하지 않는다."""
    pid = make_project(client, "wsrootdoc")
    ws = tmp_path / "proj"
    with make_session(client) as db:
        root = resolve_workspace_root(db, pid, ws, "proposal")
    assert root == ws / "proposal"
    assert not root.exists()


def test_resolve_workspace_root_ensure_creates_subdirs(client, tmp_path):
    """ensure=True — 하위 4종을 멱등 지연 생성하고 Path를 돌려준다 (str 입력 허용)."""
    pid = make_project(client, "wsrootensure")
    ws = tmp_path / "proj"
    with make_session(client) as db:
        root = resolve_workspace_root(db, pid, str(ws), "dev-design", ensure=True)
    assert root == ws / "dev-design"
    for sub in DOC_WS_SUBDIRS:
        assert (root / sub).is_dir(), sub