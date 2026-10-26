# -*- coding: utf-8 -*-
"""docloops 모듈 퍼사드 — 타 모듈의 유일한 진입점 (가이드 §3 Facade).

계약: docloops는 리프 모듈 — 이 facade가 타 모듈 facade를 import하지 않는다.
plans(승인 훅)·interview(세션 게이트)·projects(삭제 사슬·생성 시드) 쪽이
이 모듈을 호출하는 방향이다. 커밋은 호출자 트랜잭션에서 (facts.facade 패턴).
"""
from __future__ import annotations

from pathlib import Path

from app.shared.workspace import doc_ws_root, ensure_doc_ws

from .application.service import (
    DOC_KINDS,
    delete_project_data,
    doc_label,
    has_doc_layout,
    init_project_loops,
    list_loops,
    on_plan_approved,
    require_session_doc,
)
from .infrastructure.models import DocLoop, DocLoopStatus

__all__ = [
    "DocLoopStatus", "DocLoop", "DOC_KINDS", "doc_label",
    "init_project_loops", "list_loops", "require_session_doc",
    "on_plan_approved", "has_doc_layout", "delete_project_data",
    "resolve_workspace_root",
]


def resolve_workspace_root(db, project_id: int, workspace_path,
                           doc_slug: str | None, *, ensure: bool = False) -> Path:
    """프로젝트 워크스페이스 + 문서 slug → 실제 작업 루트 (doc_ws_root 위임).

    - 레이아웃 권위는 DB 행(has_doc_layout) — 디렉토리 존재로 판정하지 않는다.
    - 레거시(행 없음) 또는 doc_slug=None → 프로젝트 루트(workspace_path).
    - ensure=True면 루트 하위 구조를 멱등 지연 생성한다(ensure_doc_ws).
      derive_build의 "doc root가 다를 때만 ensure" 는 호출자가 ensure=False로
      루트를 먼저 얻고 `root != ws` 판정 후 ensure=True로 재호출해 구현한다.

    docloops는 리프 모듈 — app.shared만 import하고 타 모듈 facade는 쓰지 않는다.
    """
    ws = Path(workspace_path)
    root = doc_ws_root(ws, doc_slug,
                       doc_layout=has_doc_layout(db, project_id))
    if ensure:
        ensure_doc_ws(root)
    return root