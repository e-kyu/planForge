# -*- coding: utf-8 -*-
"""Alembic 마이그레이션 검증 — 빈 DB에서 upgrade head 시 테이블 생성.

reportagent_test DB의 alembic_version만 대상으로 한다 (drop_all과 간섭 없음).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://reportagent:reportagent@localhost:5432/reportagent_test",
)


def test_alembic_upgrade_head_creates_tables(tmp_path):
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL, "PYTHONUTF8": "1"}
    # 임시 DB를 만들어 drop → upgrade → 재적용까지 확인한다
    engine = sa.create_engine(TEST_DATABASE_URL + "_alembictest" if False else TEST_DATABASE_URL)
    with engine.connect() as c:
        c.execution_options(isolation_level="AUTOCOMMIT")
        c.execute(sa.text("DROP DATABASE IF EXISTS reportagent_alembic_test"))
        c.execute(sa.text("CREATE DATABASE reportagent_alembic_test"))
    engine.dispose()

    url = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/reportagent_alembic_test"
    try:
        for cmd in (["upgrade", "head"], ["downgrade", "base"], ["upgrade", "head"]):
            r = subprocess.run(
                [sys.executable, "-m", "alembic", *cmd],
                cwd=BACKEND_DIR, env={**env, "DATABASE_URL": url},
                capture_output=True, text=True, timeout=120,
            )
            assert r.returncode == 0, r.stdout + r.stderr
        e = sa.create_engine(url)
        with e.connect() as c:
            tables = {row[0] for row in c.execute(
                sa.text("select tablename from pg_tables where schemaname='public'"))}
        e.dispose()
        assert {"projects", "plans", "facts", "jobs", "builds", "derivatives",
                "interview_sessions", "interview_messages"} <= tables
    finally:
        engine = sa.create_engine(TEST_DATABASE_URL)
        with engine.connect() as c:
            c.execution_options(isolation_level="AUTOCOMMIT")
            c.execute(sa.text("DROP DATABASE IF EXISTS reportagent_alembic_test"))
        engine.dispose()