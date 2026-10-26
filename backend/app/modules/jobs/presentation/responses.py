# -*- coding: utf-8 -*-
"""jobs 프레젠테이션 응답 헬퍼 — 202 큐 진입 계약의 공용 조립.

enqueue(커밋 없음) + 응답 스키마 변환을 한 곳에 모은다. 호출부의 기존
`job = enqueue(...) → db.commit() → JobOut.model_validate(job)` 3줄을
그대로 대체할 수 있도록 커밋은 반환 전에 수행한다 (202 가시성 계약 —
tests/test_enqueue_visibility.py).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..facade import JobType, enqueue
from .schemas import JobOut


def enqueue_accepted(db: Session, project_id: int, job_type: JobType,
                     payload: dict) -> JobOut:
    """잡을 큐에 넣고 **반환 전에 커밋**한 뒤 202 응답 스키마로 돌려준다.

    get_db teardown 커밋은 FastAPI 특성상 응답 전송 후에 실행되어 202 직후
    /jobs refetch가 잡을 놓친다 — 커밋이 응답에 선행해야 한다는 계약이다.
    """
    job = enqueue(db, project_id, job_type, payload)
    db.commit()
    return JobOut.model_validate(job)
