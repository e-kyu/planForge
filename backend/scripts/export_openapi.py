# -*- coding: utf-8 -*-
"""OpenAPI 스키마 덤프 — 프론트 API 계약 타입 생성 원료.

실행: backend/에서 `python scripts/export_openapi.py`
→ frontend/openapi.json 갱신 후 frontend에서 `npm run gen:types`
(FastAPI 자동 스키마 → openapi-typescript — §3.1 계약 잠금)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
OUT = BACKEND_DIR.parent / "frontend" / "openapi.json"

# app을 import 가능하게 (conftest와 동일 규약)
sys.path.insert(0, str(BACKEND_DIR))


def main() -> None:
    from app.main import create_app

    app = create_app(start_worker=False)
    schema = app.openapi()
    OUT.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()