# -*- coding: utf-8 -*-
"""M2 테스트 공통 fixture — Postgres 테스트 DB + 앱 클라이언트.

전제: docker compose up -d postgres (Postgres 고정 정책).
M1 테스트(빌더·파서)는 DB를 쓰지 않으므로 영향 없다.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://reportagent:reportagent@localhost:5432/reportagent_test",
)


@pytest.fixture()
def db_env(monkeypatch, tmp_path):
    """테스트 DB + 격리된 워크스페이스 디렉토리로 환경변수를 고정한다."""
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("WORKSPACES_DIR", str(tmp_path / "workspaces"))
    return tmp_path / "workspaces"


@pytest.fixture()
def test_engine(db_env):
    from app import models  # noqa: F401 — Base.metadata에 테이블 등록 필수 (drop/create 전)
    from app.db import Base, make_engine

    engine = make_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def app(db_env, test_engine):
    from app.main import create_app

    return create_app()


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c