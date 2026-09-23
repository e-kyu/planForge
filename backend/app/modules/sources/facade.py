# -*- coding: utf-8 -*-
"""sources 모듈 퍼사드 — 타 모듈의 유일한 진입점 (가이드 §3 Facade).

fs 기반 모듈 — DB 테이블이 없고 워크스페이스 sources/ 경로만 제공한다
(인터뷰 소스 주입이 이 경로를 매 턴 읽는다, FR-2.1).
"""
from __future__ import annotations

from pathlib import Path
from sqlalchemy.orm import Session

from app.modules.projects.facade import require_project
from app.shared.workspace import ensure_workspace_dirs

__all__ = ["project_sources_dir"]


def project_sources_dir(db: Session, project_id: int) -> Path:
    """프로젝트 sources/ 디렉토리를 보장하고 반환한다."""
    p = require_project(db, project_id)
    ws = Path(p.workspace_path)
    ensure_workspace_dirs(ws)
    return ws / "sources"