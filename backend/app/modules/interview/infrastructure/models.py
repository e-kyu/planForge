# -*- coding: utf-8 -*-
"""InterviewSession·InterviewMessage 테이블 — 세션 페이즈 상태머신과 턴 이력.

이력 행은 SSE 이벤트와 같은 seq 사슬을 공유한다 (domain/events.py 참조).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.db import Base
from app.shared.types import JSONVariant, UTCDateTime, StrEnum, _enum


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

    project: Mapped["Project"] = relationship(back_populates="sessions")
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