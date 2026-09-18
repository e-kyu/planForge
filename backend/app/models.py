# -*- coding: utf-8 -*-
"""M2 데이터 모델 (SQLAlchemy 2.x).

원칙 대응:
- 원칙 4(팩트 선적립): facts 테이블 — 확정 팩트만 기록, pending은 세션 JSONB
- 원칙 5(무손실 채번): builds는 빌더 fs glob의 미러(채번 권위는 파일시스템), 절대 재사용 없음
- 원칙 1(SSOT): plans.markdown이 콘텐츠 유일 원본, work/*.json은 derivatives.json 미러 + 파생물 재생성만
- 추적성(§5): builds → derivative_id → plan_id 역참조 사슬
"""
from __future__ import annotations

import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .db import Base

# 테스트가 임시로 다른 방언(SQLite 등)을 쓰지 않는다 — PostgreSQL 고정(사용자 결정).
# JSONB를 그대로 쓰되, alembic/모델 모두 postgres 전용 타입으로 유지한다.
JSONVariant = JSONB().with_variant(JSON(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StrEnum(str, enum.Enum):
    """native_enum=False String Enum 공통 베이스 (PG enum 마이그레이션 부담 회피)."""

    def __str__(self) -> str:  # pragma: no cover - 표기 편의
        return self.value


def _enum(enum_cls, **kw):
    return Enum(enum_cls, native_enum=False, length=32, **kw)


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class SessionPhase(StrEnum):
    HYPOTHESIS = "hypothesis"
    AWAITING_ANSWERS = "awaiting_answers"
    FACT_GATE = "fact_gate"
    KEY_MESSAGE_GATE = "key_message_gate"
    PLAN_REVIEW = "plan_review"
    APPROVED = "approved"
    FAILED = "failed"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    DONE = "done"
    ABORTED = "aborted"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"
    EVENT = "event"


class MessageKind(StrEnum):
    TEXT = "text"
    QUESTIONS = "questions"
    FACTS = "facts"
    KEY_MESSAGES = "key_messages"
    PLAN_DRAFT = "plan_draft"
    STATE = "state"
    NOTICE = "notice"
    ERROR = "error"
    TOOL_CALL = "tool_call"


class FactStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class FactOrigin(StrEnum):
    INTERVIEW = "interview"
    REVIEW = "review"
    MANUAL = "manual"


class PlanStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class PlanOrigin(StrEnum):
    INTERVIEW = "interview"
    EDIT = "edit"


class DerivativeKind(StrEnum):
    SLIDES = "slides"
    REPORT = "report"


class JobType(StrEnum):
    DERIVE_BUILD = "derive_build"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobErrorClass(StrEnum):
    VALIDATION = "validation"
    SCHEMA = "schema"
    LLM = "llm"
    BUILDER = "builder"
    INTERNAL = "internal"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[ProjectStatus] = mapped_column(
        _enum(ProjectStatus), default=ProjectStatus.ACTIVE, server_default="active"
    )
    owner: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 추후 접근제어 확장(§5)
    workspace_path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")

    sessions: Mapped[list["InterviewSession"]] = relationship(back_populates="project")


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    phase: Mapped[SessionPhase] = mapped_column(
        _enum(SessionPhase), default=SessionPhase.HYPOTHESIS, server_default="hypothesis"
    )
    round_no: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[SessionStatus] = mapped_column(
        _enum(SessionStatus), default=SessionStatus.ACTIVE, server_default="active"
    )
    pending_questions: Mapped[list | None] = mapped_column(JSONVariant, nullable=True)
    pending_facts: Mapped[list | None] = mapped_column(JSONVariant, nullable=True)
    pending_key_messages: Mapped[list | None] = mapped_column(JSONVariant, nullable=True)
    checklist: Mapped[list | None] = mapped_column(JSONVariant, nullable=True)
    key_messages_approved: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    hypothesis: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    llm_turns: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")

    project: Mapped[Project] = relationship(back_populates="sessions")
    messages: Mapped[list["InterviewMessage"]] = relationship(
        back_populates="session", order_by="InterviewMessage.seq"
    )


class InterviewMessage(Base):
    __tablename__ = "interview_messages"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_session_seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("interview_sessions.id"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)  # 세션별 단조 — SSE 재접속 커서
    role: Mapped[MessageRole] = mapped_column(_enum(MessageRole))
    kind: Mapped[MessageKind] = mapped_column(_enum(MessageKind))
    content: Mapped[str] = mapped_column(Text, default="", server_default="")
    payload: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")

    session: Mapped[InterviewSession] = relationship(back_populates="messages")


class Fact(Base):
    __tablename__ = "facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("interview_sessions.id"), nullable=True
    )
    date: Mapped[date] = mapped_column(Date, default=date.today)
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(300), default="", server_default="")
    status: Mapped[FactStatus] = mapped_column(
        _enum(FactStatus), default=FactStatus.ACTIVE, server_default="active"
    )
    origin: Mapped[FactOrigin] = mapped_column(
        _enum(FactOrigin), default=FactOrigin.INTERVIEW, server_default="interview"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("project_id", "version_no", name="uq_project_planver"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)  # 1부터, project별 독립
    markdown: Mapped[str] = mapped_column(Text)  # 원칙 1 — SSOT
    docs: Mapped[list | None] = mapped_column(JSONVariant, nullable=True)  # 파싱 캐시
    parsed_ok: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PlanStatus] = mapped_column(
        _enum(PlanStatus), default=PlanStatus.DRAFT, server_default="draft"
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    origin: Mapped[PlanOrigin] = mapped_column(
        _enum(PlanOrigin), default=PlanOrigin.INTERVIEW, server_default="interview"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class Derivative(Base):
    __tablename__ = "derivatives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)  # 세대 바인딩
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[DerivativeKind] = mapped_column(_enum(DerivativeKind))
    doc: Mapped[str] = mapped_column(String(100))
    json: Mapped[dict] = mapped_column(JSONVariant)  # work/*.json 미러 (재생성 원본은 plan)
    slides_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sections_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    unconfirmed: Mapped[list | None] = mapped_column(JSONVariant, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class Build(Base):
    __tablename__ = "builds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)
    derivative_id: Mapped[int] = mapped_column(ForeignKey("derivatives.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    doc_kind: Mapped[str] = mapped_column(String(100))
    ext: Mapped[str] = mapped_column(String(8))
    version_no: Mapped[int] = mapped_column(Integer)  # 빌더 fs glob의 미러
    title: Mapped[str] = mapped_column(String(300))
    file_path: Mapped[str] = mapped_column(String(500))  # 워크스페이스 상대 경로
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    type: Mapped[JobType] = mapped_column(_enum(JobType))
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus), default=JobStatus.QUEUED, server_default="queued"
    )
    payload: Mapped[dict] = mapped_column(JSONVariant)
    result: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    error_class: Mapped[JobErrorClass | None] = mapped_column(_enum(JobErrorClass), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")