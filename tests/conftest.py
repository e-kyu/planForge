# -*- coding: utf-8 -*-
"""테스트 공통 fixture — SQLite 테스트 DB(테스트별 임시 파일) + 앱 클라이언트.

테스트마다 tmp_path 아래 독립 DB 파일을 만들어 완전 격리한다 — 저장소에 DB 파일이
남지 않고 테스트 간 상태 공유도 없다. M1 테스트(빌더·파서)는 DB를 쓰지 않으므로 영향 없다.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture()
def db_env(monkeypatch, tmp_path):
    """테스트 DB(임시 파일) + 격리된 워크스페이스 디렉토리로 환경변수를 고정한다."""
    # TEST_DATABASE_URL 환경변수로 오버라이드 가능 (확장점 — 기본은 테스트별 tmp SQLite)
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("WORKSPACES_DIR", str(tmp_path / "workspaces"))
    return tmp_path / "workspaces"


@pytest.fixture()
def test_engine(db_env):
    import app.modules  # noqa: F401 — Base.metadata에 모든 모듈 테이블 등록 필수 (drop/create 전)
    from app.shared import db as app_db
    from app.shared.db import Base, make_engine

    engine = make_engine(os.environ["DATABASE_URL"])
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
    # make_session_factory가 캐시한 엔진까지 정리 — 임시 DB 파일 핸들 해제
    app_db.dispose_cached_engines()


@pytest.fixture()
def app(db_env, test_engine):
    from app.main import create_app

    # 워커 루프 비활성 — 테스트는 run_job을 직접 호출해 결정론적으로 검증한다
    return create_app(start_worker=False)


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c