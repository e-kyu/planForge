# -*- coding: utf-8 -*-
"""pytest가 backend/reportagent 패키지를 import할 수 있게 경로를 추가한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))