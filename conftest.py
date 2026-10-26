# -*- coding: utf-8 -*-
"""pytest가 독립 CLI 패키지의 planforge·backend의 app 패키지를 import할 수 있게 경로를 추가한다.

`packages/planforge-cli/src`를 가장 먼저 둔다 — `backend/planforge`에는 `__init__.py`가
없는 설정 디렉토리만 남아 namespace package가 되므로, 정규 패키지가 항상 우선해야 한다.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT / "backend"))
sys.path.insert(0, str(_ROOT / "packages" / "planforge-cli" / "src"))
