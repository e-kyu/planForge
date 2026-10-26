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
    "session_doc_slugs", "delete_project_data",
]


def get_session(db: Session, session_id: int) -> InterviewSession | None:
    return db.get(InterviewSession, session_id)


def require_session(db: Session, session_id: int) -> InterviewSession:
    s = get_session(db, session_id)
    if s is None:
        raise http_404(f"세션 없음: {session_id}")
    return s


def complete_plan_review_sessions(db: Session, project_id: int,
                                  doc_slug: str | None = None) -> None:
    """plan 승인(plans 모듈)이 호출 — plan을 작성한 세션을 완료 처리한다.

    doc_slug를 주면 그 문서 세션만, 주지 않으면 기존 동작(전체)을 유지한다 —
    레거시 plan 승인 경로와 기존 테스트 계약이 None=전체에 고정돼 있다 (문서 plan
    승인은 plans 쪽이 slug를 명시적으로 넘긴다).
    """
    q = select(InterviewSession).where(
        InterviewSession.project_id == project_id,
        InterviewSession.phase == SessionPhase.PLAN_REVIEW)
    if doc_slug is not None:
        q = q.where(InterviewSession.doc_slug == doc_slug)
    for sess in db.scalars(q).all():
        sess.phase = SessionPhase.APPROVED
        sess.status = SessionStatus.DONE


def session_doc_slugs(db: Session, project_id: int) -> dict[int, str | None]:
    """세션 id → 문서 slug 매핑 (facts 모듈이 호출 — compact 미러 소속 판정용).

    doc_slug None = 레거시 세션(워크스페이스 루트 미러 소속).
    """
    return {sid: doc_slug for sid, doc_slug in db.execute(
        select(InterviewSession.id, InterviewSession.doc_slug).where(
            InterviewSession.project_id == project_id)).all()}


def delete_project_data(db: Session, project_id: int) -> None:
    """프로젝트 삭제 사슬 — 이력 행을 세션보다 먼저 지운다 (자식 → 부모)."""
    db.execute(delete(InterviewMessage).where(
        InterviewMessage.session_id.in_(
            select(InterviewSession.id).where(InterviewSession.project_id == project_id)
        )
    ))
    db.execute(delete(InterviewSession).where(InterviewSession.project_id == project_id))