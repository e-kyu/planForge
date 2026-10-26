# -*- coding: utf-8 -*-
"""OpenAPI 스키마 덤프 — 프론트 API 계약 타입 생성 원료 (호환 shim).

실행: backend/에서 `python scripts/export_openapi.py`
→ frontend/openapi.json 갱신 후 frontend에서 `npm run gen:types`
(FastAPI 자동 스키마 → openapi-typescript — §3.1 계약 잠금)

본체는 `scripts/admin.py`의 `openapi` 서브커맨드다 — 기존 실행 경로만 유지한다.
"""
from __future__ import annotations

import sys

from admin import main as _admin_main


def main() -> int:
    return _admin_main(["openapi"])


if __name__ == "__main__":
    sys.exit(main())
