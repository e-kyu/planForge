# -*- coding: utf-8 -*-
"""Alembic 환경 — app.modules 모델 메타데이터를 사용한다."""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# backend/를 import 경로에 추가 (app, planforge 모두)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.modules  # noqa: E402,F401  (모든 모듈 models — metadata 등록)
from app.shared.db import Base, ensure_sqlite_dir  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    # app.shared.config 기본값으로 폴백 — alembic.ini의 URL과 드리프트하지 않는다
    from app.shared.config import get_settings  # noqa: E402

    database_url = get_settings().database_url
if database_url.startswith("sqlite"):
    ensure_sqlite_dir(database_url)
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # render_as_batch — SQLite는 ALTER TABLE 제약이 커서 스키마 변경에 batch 모드가 필요하다
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()