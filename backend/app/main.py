# -*- coding: utf-8 -*-
"""FastAPI 앱 팩토리 (M2).

create_app(llm_overrides=None) — 테스트는 llm_overrides로 fake LLM을 주입한다.
"""
from __future__ import annotations

from fastapi import FastAPI

from .api import api_router
from .config import get_settings
from .db import make_engine
from .errors import install_error_handlers
from .models import Base


def create_app(llm_overrides: dict | None = None) -> FastAPI:
    settings = get_settings()

    # llm_overrides는 PR-3(LLMRegistry)에서 사용 — 미리 받아두어 API 시그니처 고정
    app = FastAPI(
        title="report-agent",
        version="0.2.0",
        description="기획 문서 생성 에이전트 웹 서비스 (M2 백엔드)",
    )
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.state.llm_overrides = llm_overrides or {}

    install_error_handlers(app)
    app.include_router(api_router)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app


def init_db(engine) -> None:
    """개발용 헬퍼 — 운영은 alembic upgrade head를 사용한다."""
    Base.metadata.create_all(engine)


app = None


def get_app() -> FastAPI:
    global app
    if app is None:
        app = create_app()
    return app