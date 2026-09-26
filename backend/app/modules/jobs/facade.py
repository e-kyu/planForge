# -*- coding: utf-8 -*-
"""jobs 모듈 퍼사드 — 타 모듈의 유일한 진입점 (가이드 §3 Facade).

큐 진입(plans·derivatives·review의 POST)과 프로젝트 삭제 사이즈의
busy 검사·정리가 이 퍼사드를 경유한다.
"""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .infrastructure.models import Job, JobErrorClass, JobStatus, JobType

__all__ = ["JobType", "JobStatus", "JobErrorClass", "enqueue", "has_busy_jobs",
           "delete_project_jobs"]


def enqueue(db: Session, project_id: int | None, job_type: JobType, payload: dict) -> Job:
    """큐 진입 — 커밋은 호출자 트랜잭션에서 (단일 워커가 클레임한다)."""
    job = Job(project_id=project_id, type=job_type, payload=payload)
    db.add(job)
    db.flush()
    return job


def has_busy_jobs(db: Session, project_id: int) -> bool:
    """대기/실행 중 job 존재 — 프로젝트 삭제 전 필수 검사 (실행 도중 소실 방지)."""
    busy = db.scalar(
        select(func.count()).select_from(Job).where(
            Job.project_id == project_id,
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
    )
    return bool(busy)


def delete_project_jobs(db: Session, project_id: int) -> None:
    db.execute(delete(Job).where(Job.project_id == project_id))