# -*- coding: utf-8 -*-
"""공용 파일 I/O — UTF-8(BOM 허용) 텍스트·JSON 읽기/쓰기.

동작 불변 계약: write_json은 기존 `json.dumps(obj, ensure_ascii=False, indent=2)` +
utf-8 기록과 **바이트 동일**하다 — trailing newline을 붙이지 않는다.
읽기는 utf-8-sig를 쓴다 (BOM이 있으면 제거, 없으면 utf-8과 동일).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_text_utf8(path: str | Path) -> str:
    """UTF-8 텍스트 읽기 — BOM이 있으면 제거한다 (utf-8-sig)."""
    return Path(path).read_text(encoding="utf-8-sig")


def read_json(path: str | Path) -> Any:
    """UTF-8(BOM 허용) JSON 파일 읽기."""
    return json.loads(read_text_utf8(path))


def write_json(path: str | Path, obj: Any) -> Path:
    """UTF-8 JSON 쓰기 — ensure_ascii=False·indent=2, trailing newline 없음."""
    p = Path(path)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
