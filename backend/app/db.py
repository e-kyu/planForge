# -*- coding: utf-8 -*-
"""DB 엔진·세션 팩토리 (SQLAlchemy 2.x, SQLite 단일 방언)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def ensure_sqlite_dir(database_url: str) -> None:
    """SQLite 파일 DB의 부모 디렉토리를 보장한다 (앱 진입점·alembic env.py 공용)."""
    db_path = make_url(database_url).database
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def _attach_sqlite_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, _record):  # 연결마다 1회
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")    # FK 강제 (SQLite는 기본 OFF)
        cur.execute("PRAGMA journal_mode=WAL")   # 읽기·쓰기 동시성
        cur.execute("PRAGMA busy_timeout=5000")  # 쓰기 잠금 대기
        cur.close()


def make_engine(database_url: str) -> Engine:
    """항상 새 엔진을 만든다 (conftest 전용 — 앱·워커는 get_engine 캐시를 쓴다)."""
    if database_url.startswith("sqlite"):
        ensure_sqlite_dir(database_url)
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            # FastAPI 스레드풀·SSE 워커 스레드가 풀 커넥션을 공유하므로 필수
            connect_args={"check_same_thread": False},
        )
        _attach_sqlite_pragmas(engine)
        return engine
    return create_engine(database_url, pool_pre_ping=True)


# 앱·워커·SSE 브릿지가 URL별 단일 엔진을 재사용한다 (요청마다 엔진 생성 금지)
_engines: dict[str, Engine] = {}


def get_engine(database_url: str) -> Engine:
    engine = _engines.get(database_url)
    if engine is None:
        engine = make_engine(database_url)
        _engines[database_url] = engine
    return engine


def dispose_cached_engines() -> None:
    """캐시된 엔진 정리 — 테스트 teardown이 임시 DB 파일 핸들을 놓게 한다."""
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()


def make_session_factory(database_url: str) -> sessionmaker:
    return sessionmaker(bind=get_engine(database_url), expire_on_commit=False)


def get_db():
    """FastAPI 의존성 — 요청 스코프 세션."""
    settings = get_settings()
    SessionLocal = make_session_factory(settings.database_url)
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()