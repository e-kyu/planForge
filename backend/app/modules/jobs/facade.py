# -*- coding: utf-8 -*-
"""jobs 모듈 퍼사드 — 타 모듈의 유일한 진입점 (가이드 §3 Facade).

큐 진입(plans·derivatives·review의 POST)과 프로젝트 삭제 사이즈의
busy 검사·정리가 이 퍼사드를 경유한다.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .infrastructure.models import Job, JobErrorClass, JobStatus, JobType

__all__ = ["JobType", "JobStatus", "JobErrorClass", "enqueue", "has_busy_jobs",
           "list_active", "delete_project_jobs", "report_progress"]


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


def list_active(db: Session, project_id: int, job_type: JobType) -> list[Job]:
    """대기/실행 중인 특정 타입 잡 목록 — 자동 큐잉 중복 방지 등 파이프라인 정책용
    조회 (잡 테이블 접근을 이 퍼사드 안에 둔다)."""
    jobs = db.scalars(
        select(Job).where(
            Job.project_id == project_id,
            Job.type == job_type,
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
    ).all()
    return list(jobs)


def delete_project_jobs(db: Session, project_id: int) -> None:
    db.execute(delete(Job).where(Job.project_id == project_id))


def report_progress(db: Session, job: Job, step: str, *,
                    attempt: int | None = None, max_attempts: int | None = None,
                    detail: str | None = None) -> None:
    """실행 중 job의 진행 상태를 기록하고 즉시 커밋한다 (running 잡 폴링용).

    계약:
    - 세션 전체를 커밋한다 — 호출 시점에 대기 중인 도메인 행 생성/변경이 없어야 한다
      (조기 커밋으로 빌드 실패 시 고아 행이 남는다).
    - job.status는 RUNNING이어야 하며, status 전이는 worker가 소유한다 — 여기서 건드리지 않는다.
    - 예외 방어는 caller가 한다 — 진행 기록 실패가 작업 자체를 죽이지 않게.
    """
    job.progress = {"step": step, "detail": detail, "attempt": attempt,
                    "max_attempts": max_attempts,
                    "at": datetime.now(timezone.utc).isoformat()}
    db.commit()