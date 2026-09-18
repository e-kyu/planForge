# -*- coding: utf-8 -*-
"""DB 엔진·세션 팩토리 (SQLAlchemy 2.x)."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True)


def make_session_factory(database_url: str) -> sessionmaker:
    return sessionmaker(bind=make_engine(database_url), expire_on_commit=False)


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