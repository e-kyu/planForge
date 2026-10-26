# -*- coding: utf-8 -*-
"""backend/scripts 공용 부트스트랩 — import 경로와 DB URL 해석.

`packages/planforge-cli/src`를 sys.path 최우선으로 둔다. `backend/planforge`에는
`__init__.py`가 없는 설정 디렉토리만 남아 namespace package가 되므로, 정규 패키지가
항상 먼저 발견돼야 한다 (conftest.py와 동일 규약).
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
PACKAGE_SRC = REPO_ROOT / "packages" / "planforge-cli" / "src"


def ensure_paths() -> None:
    """PACKAGE_SRC를 sys.path 최우선, BACKEND_DIR를 그 다음에 둔다."""
    for entry in (str(BACKEND_DIR), str(PACKAGE_SRC)):
        if entry in sys.path:
            sys.path.remove(entry)
    sys.path.insert(0, str(BACKEND_DIR))
    sys.path.insert(0, str(PACKAGE_SRC))


def database_url() -> str:
    """웹 설정과 동일한 DB URL 해석 (DATABASE_URL > 루트 data/planforge.db)."""
    from app.shared.config import Settings

    return Settings().database_url
