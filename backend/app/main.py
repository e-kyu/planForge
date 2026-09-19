# -*- coding: utf-8 -*-
"""FastAPI 앱 팩토리 (M2).

create_app(llm_overrides=None) — 테스트는 llm_overrides로 fake LLM을 주입한다.
"""
from __future__ import annotations

from fastapi import FastAPI

from .api import api_router
from .config import get_settings
from .db import get_engine
from .errors import install_error_handlers
from .models import Base


def create_app(llm_overrides: dict | None = None, start_worker: bool = True) -> FastAPI:
    from contextlib import asynccontextmanager

    from .db import make_session_factory
    from .worker import JobContext, worker_loop

    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 단일 백그라운드 워커 — 빌드 직렬화의 구조적 보장 (worker.py 모듈 주석 참조)
        task = None
        if start_worker:
            ctx = JobContext(
                session_factory=make_session_factory(settings.database_url),
                settings=settings,
                llm_overrides=app.state.llm_overrides,
            )
            import asyncio

            task = asyncio.create_task(worker_loop(ctx))
        yield
        if task is not None:
            task.cancel()

    app = FastAPI(
        title="report-agent",
        version="0.2.0",
        description="기획 문서 생성 에이전트 웹 서비스 (M2 백엔드)",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = get_engine(settings.database_url)
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


# 확정 명령(`uvicorn app.main:app --reload`)용 모듈 레벨 인스턴스.
# 테스트는 create_app(llm_overrides=...) 팩토리를 직접 쓴다.
app = create_app()