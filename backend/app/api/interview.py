# -*- coding: utf-8 -*-
"""인터뷰 세션 API (FR-2).

변경 POST(kick/answers/facts-confirm/key-messages)는 그 턴의 SSE 스트림을 직접 반환한다(D6).
LLM 턴 실행은 PR-4 상태머신(interview.py)에서 연결된다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import http_404
from ..models import (
    InterviewMessage,
    InterviewSession,
    MessageKind,
    MessageRole,
    Project,
    SessionPhase,
    SessionStatus,
)

router = APIRouter(tags=["interview"])


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    phase: str
    round_no: int
    status: str
    pending_questions: list | None
    pending_facts: list | None
    pending_key_messages: list | None
    checklist: list | None
    key_messages_approved: bool
    hypothesis: dict | None
    error: str | None
    created_at: object


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    role: str
    kind: str
    content: str
    payload: dict | None
    created_at: object


class SessionCreate(BaseModel):
    pass


def _session_or_404(db: Session, sid: int) -> InterviewSession:
    s = db.get(InterviewSession, sid)
    if s is None:
        raise http_404(f"세션 없음: {sid}")
    return s


@router.post("/api/projects/{project_id}/interview/sessions", status_code=201)
def create_session(project_id: int, _body: SessionCreate, db: Session = Depends(get_db)):
    if db.get(Project, project_id) is None:
        raise http_404(f"프로젝트 없음: {project_id}")
    s = InterviewSession(project_id=project_id)
    db.add(s)
    db.flush()
    return SessionOut.model_validate(s)


@router.get("/api/interview/sessions/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)):
    return SessionOut.model_validate(_session_or_404(db, session_id))


@router.get("/api/interview/sessions/{session_id}/messages", response_model=list[MessageOut])
def list_messages(session_id: int, after: int = 0, db: Session = Depends(get_db)):
    """트랜스크립트 + SSE 재접속 리플레이 커서 (D4/D6)."""
    _session_or_404(db, session_id)
    msgs = db.scalars(
        select(InterviewMessage)
        .where(InterviewMessage.session_id == session_id, InterviewMessage.seq > after)
        .order_by(InterviewMessage.seq)
    )
    return [MessageOut.model_validate(m) for m in msgs]


# ---------------------------------------------------------------- 이력 영속 헬퍼 (에이전트가 사용)

def next_seq(db: Session, session_id: int) -> int:
    """세션별 단조 seq — SSE 커서. 동시 턴은 세션 락(409)으로 직렬화되므로 안전."""
    cur = db.scalar(
        select(InterviewMessage.seq)
        .where(InterviewMessage.session_id == session_id)
        .order_by(InterviewMessage.seq.desc())
        .limit(1)
    )
    return (cur or 0) + 1


def append_message(db: Session, session_id: int, role: MessageRole, kind: MessageKind,
                   content: str = "", payload: dict | None = None) -> int:
    """이력 행 적립 → seq 반환. 커밋은 턴 트랜잭션에서."""
    seq = next_seq(db, session_id)
    db.add(InterviewMessage(session_id=session_id, seq=seq, role=role, kind=kind,
                            content=content, payload=payload))
    return seq