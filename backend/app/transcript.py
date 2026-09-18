# -*- coding: utf-8 -*-
"""인터뷰 트랜스크립트 영속 헬퍼 — api/agents 양쪽에서 공용 (순환 import 회피).

모든 이벤트는 interview_messages 행으로 기록되어 GET /messages?after=seq 재접속
리플레이(D6)가 된다. SSE 라이브 스트림과 이력 행은 같은 seq 사슬을 공유한다.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import InterviewMessage, MessageKind, MessageRole


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