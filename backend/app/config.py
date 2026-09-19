# -*- coding: utf-8 -*-
"""웹 백엔드 설정 (환경변수 기반 — §3.1 배포: Docker Compose)."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
# 런타임 DB 파일 — workspaces/·sources/와 같은 레벨(저장소 루트)의 data/
DATA_DIR = BACKEND_DIR.parent / "data"


class Settings:
    """환경변수에서 읽는 런타임 설정. 테스트에서는 필드를 직접 교체한다."""

    def __init__(self) -> None:
        self.database_url: str = os.environ.get(
            "DATABASE_URL",
            f"sqlite:///{(DATA_DIR / 'reportagent.db').as_posix()}",
        )
        self.workspaces_dir: Path = Path(
            os.environ.get("WORKSPACES_DIR", BACKEND_DIR.parent / "workspaces")
        )
        # M1 LLM 설정과 동일한 해석 순서 (REPORTAGENT_CONFIG > 기본 경로)
        self.llm_config_path: Path = Path(
            os.environ.get("REPORTAGENT_CONFIG", BACKEND_DIR / "reportagent" / "config.json")
        )
        # 인터뷰 소스 확인용 글로벌 sources (plan-doc: 글로벌 sources/ + 프로젝트 sources/)
        self.global_sources_dir: Path = Path(
            os.environ.get("GLOBAL_SOURCES_DIR", BACKEND_DIR.parent / "sources")
        )
        self.sse_keepalive_seconds: int = int(os.environ.get("SSE_KEEPALIVE_SECONDS", "15"))


def get_settings() -> Settings:
    return Settings()