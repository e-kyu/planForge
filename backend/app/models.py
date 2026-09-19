# -*- coding: utf-8 -*-
"""M2 데이터 모델 (SQLAlchemy 2.x).

원칙 대응:
- 원칙 4(팩트 선적립): facts 테이블 — 확정 팩트만 기록, pending은 세션 JSON
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
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator

from .db import Base

# SQLite 단일 방언 (2026-09-19 전환) — 방언 분기(with_variant) 없이 JSON 하나로 통일.
JSONVariant = JSON


class UTCDateTime(TypeDecorator):
    """DateTime(timezone=True) 시맨틱을 SQLite에 맞춘다.

    저장: aware → UTC 변환 후 naive 기록 (SQLite는 tz 보존 불가)
    로드: naive → UTC aware 부여 — 기존 timestamptz 계약(aware 반환) 유지,
    Pydantic이 +00:00 오프셋을 실어 직렬화한다.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class StrEnum(str, enum.Enum):
    """native_enum=False String Enum 공통 베이스 (SQLite에는 네이티브 ENUM 타입이 없다)."""

    def __str__(self) -> str:  # pragma: no cover - 표기 편의
        return self.value


def _enum(enum_cls, **kw):
    # value 기준 저장 (기본은 name 저장 — 'queued'가 'QUEUED'로 기록되는 문제 방지)
    return Enum(enum_cls, values_callable=lambda e: [m.value for m in e],
                native_enum=False, length=32, **kw)


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
    REVIEW = "review"


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
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

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
        Boolean, default=False, server_default=text("0")
    )
    hypothesis: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    llm_turns: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

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
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

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
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("project_id", "version_no", name="uq_project_planver"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)  # 1부터, project별 독립
    markdown: Mapped[str] = mapped_column(Text)  # 원칙 1 — SSOT
    docs: Mapped[list | None] = mapped_column(JSONVariant, nullable=True)  # 파싱 캐시
    parsed_ok: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PlanStatus] = mapped_column(
        _enum(PlanStatus), default=PlanStatus.DRAFT, server_default="draft"
    )
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    origin: Mapped[PlanOrigin] = mapped_column(
        _enum(PlanOrigin), default=PlanOrigin.INTERVIEW, server_default="interview"
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())


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
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())


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
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())


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
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())


class ReviewReport(Base):
    """검수 리포트 (FR-4) — plan 세대 1개당 검수 결과 1건 이상.

    findings는 numcheck.Finding + LLM 발견사항을 통합한 리스트
    [{code, severity, where, message, suggestion?}]. 심각도: red(사실 오류·수치
    불일치) / yellow(표현·구조) / white(선택). 수정은 plan 세대 교체(revise→approve)
    후 파생물 재생성으로만 한다 (FR-4.3 — 파생물 직접 수정 금지).
    """

    __tablename__ = "review_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)  # 검수 대상 세대
    findings: Mapped[list] = mapped_column(JSONVariant, default=list)
    red_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    yellow_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    white_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    llm_ok: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())