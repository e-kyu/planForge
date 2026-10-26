# -*- coding: utf-8 -*-
"""LLM 설정 파일 경로 해석 — 기존 CLI 동작 보존.

우선순위:
1. explicit (`--config`)
2. `PLANFORGE_CONFIG` 환경변수
3. `Path.cwd() / "planforge" / "config.json"` — 문서화된 실행 위치가 `backend/`이므로
   기존 기본 경로(`backend/planforge/config.json`)와 동일하다.
4. 패키지 디렉토리 인접 `config.json` (설치 환경 폴백)

3·4는 존재하는 후보를 먼저 택하고, 둘 다 없으면 3의 경로를 반환한다 — 호출자가
`is_file()`로 안내 메시지를 낸다 (기존 `cmd_derive` 동작).
"""
from __future__ import annotations

import os
from pathlib import Path

# planforge 패키지 루트 (…/planforge) — 설치 환경의 인접 config.json 폴백.
PACKAGE_DIR = Path(__file__).resolve().parent.parent


def resolve_config_path(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("PLANFORGE_CONFIG")
    if env:
        return Path(env)
    cwd_candidate = Path.cwd() / "planforge" / "config.json"
    package_candidate = PACKAGE_DIR / "config.json"
    for candidate in (cwd_candidate, package_candidate):
        if candidate.is_file():
            return candidate
    return cwd_candidate
