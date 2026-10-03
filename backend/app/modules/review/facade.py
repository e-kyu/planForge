# -*- coding: utf-8 -*-
"""review 모듈 퍼사드 — 타 모듈의 유일한 진입점 (가이드 §3 Facade)."""
from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.modules.jobs.facade import JobType, enqueue, list_active

from .infrastructure.models import ReviewReport

__all__ = ["get_report", "delete_project_data", "enqueue_auto_review"]


def get_report(db: Session, review_id: int) -> ReviewReport | None:
    return db.get(ReviewReport, review_id)


def delete_project_data(db: Session, project_id: int) -> None:
    db.execute(delete(ReviewReport).where(ReviewReport.project_id == project_id))


def enqueue_auto_review(db: Session, project_id: int, plan_id: int) -> object | None:
    """수치 위반이 잔여한 채 끝난 derive 뒤에 붙이는 자동 검수 큐잉 (결정 17).

    수치 무결성 판정 권위는 검수 단계에 있다 — derive는 측정만 하고 red를 남기면
    검수 잡을 큐에 넣어 리포트까지 자동으로 닫는다. 같은 plan 세대의 활성
    (queued/running) 검수 잡이 이미 있으면 중복 큐잉하지 않고 None을 반환한다.
    커밋은 호출자 트랜잭션 — derive_build의 도메인 행 기록과 같은 커밋으로 묶인다
    (크래시 시 'done인데 검수 잡 없음' 창 제거). 반환값은 jobs.facade.enqueue가
    만든 Job 행(호출자는 참값 여부만 판단) — 타 모듈 테이블 직접 import 금지 규칙상
    모델 타입을 대지 않는다.
    """
    active = list_active(db, project_id, JobType.REVIEW)
    if any((j.payload or {}).get("plan_id") == plan_id for j in active):
        return None
    return enqueue(db, project_id, JobType.REVIEW, {"plan_id": plan_id, "auto": True})