# -*- coding: utf-8 -*-
"""interview 모듈 퍼사드 — 타 모듈의 유일한 진입점 (가이드 §3 Facade)."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.shared.errors import http_404

from .infrastructure.models import (
    InterviewMessage,
    InterviewSession,
    MessageKind,
    MessageRole,
    SessionPhase,
    SessionStatus,
)

__all__ = [
    "SessionPhase", "SessionStatus", "MessageRole", "MessageKind",
    "get_session", "require_session", "complete_plan_review_sessions",
    "delete_project_data",
]


def get_session(db: Session, session_id: int) -> InterviewSession | None:
    return db.get(InterviewSession, session_id)


def require_session(db: Session, session_id: int) -> InterviewSession:
    s = get_session(db, session_id)
    if s is None:
        raise http_404(f"세션 없음: {session_id}")
    return s


def complete_plan_review_sessions(db: Session, project_id: int) -> None:
    """plan 승인(plans 모듈)이 호출 — plan을 작성한 세션을 완료 처리한다."""
    for sess in db.scalars(
        select(InterviewSession)
        .where(InterviewSession.project_id == project_id,
               InterviewSession.phase == SessionPhase.PLAN_REVIEW)
    ).all():
        sess.phase = SessionPhase.APPROVED
        sess.status = SessionStatus.DONE


def delete_project_data(db: Session, project_id: int) -> None:
    """프로젝트 삭제 사슬 — 이력 행을 세션보다 먼저 지운다 (자식 → 부모)."""
    db.execute(delete(InterviewMessage).where(
        InterviewMessage.session_id.in_(
            select(InterviewSession.id).where(InterviewSession.project_id == project_id)
        )
    ))
    db.execute(delete(InterviewSession).where(InterviewSession.project_id == project_id))