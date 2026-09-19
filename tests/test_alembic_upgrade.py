# -*- coding: utf-8 -*-
"""Alembic 마이그레이션 검증 — 빈 SQLite 파일에서 upgrade head 시 테이블 생성."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"


def _run_alembic(cmd: list[str], url: str) -> None:
    r = subprocess.run(
        [sys.executable, "-m", "alembic", *cmd],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": url, "PYTHONUTF8": "1"},
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_alembic_upgrade_head_creates_tables(tmp_path):
    url = f"sqlite:///{(tmp_path / 'alembic_test.db').as_posix()}"
    # upgrade → downgrade → upgrade 사이클 전체가 성공해야 한다
    for cmd in (["upgrade", "head"], ["downgrade", "base"], ["upgrade", "head"]):
        _run_alembic(cmd, url)

    engine = sa.create_engine(url)
    try:
        with engine.connect() as c:
            tables = {row[0] for row in c.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type='table'"))}
    finally:
        engine.dispose()
    assert {"projects", "plans", "facts", "jobs", "builds", "derivatives",
            "interview_sessions", "interview_messages", "review_reports"} <= tables