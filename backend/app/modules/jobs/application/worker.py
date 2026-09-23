# -*- coding: utf-8 -*-
"""DB 기반 작업 큐 — 단일 워커 직렬 실행 (§3.1, 원칙 5).

- 빌드 동시성이 거의 없는 팀 단위 서비스(1~10명)라 Redis/Celery 없이 job 테이블 + 단일 워커.
- 빌더(build_ppt.BLANK_LAYOUT_IDX 모듈 전역)는 스레드 안전하지 않으므로
  **절대 병렬 실행 금지** — 워커 태스크가 1개이고 run_job은 단일 스레드에서 직렬 실행된다.

핸들러는 각 결과 모듈의 application에 산다 (큐 역학만 이 모듈이 소유한다):
- derive_build → app.modules.derivatives.application.derive_build
- review       → app.modules.review.application.run_review
- plan_revise  → app.modules.plans.application.plan_revise_job
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from planforge.derive import DeriveError
from planforge.plan import PlanError

from ..infrastructure.models import Job, JobErrorClass, JobStatus


@dataclass
class JobContext:
    """run_job 실행 컨텍스트 — 테스트에서 LLM을 주입하려면 llm_overrides를 쓴다."""

    session_factory: sessionmaker
    settings: object
    llm_overrides: dict | None = None


def claim_next_job(session: Session) -> Job | None:
    """큐에서 다음 job을 클레임한다.

    SQLite 전환(2026-09-19): FOR UPDATE SKIP LOCKED는 SQLite 미지원이라 제거했다.
    워커는 정확히 1개(lifespan asyncio 태스크 1개, run_job은 단일 스레드 직렬)이므로
    '조회 → running 전이' 경쟁이 존재하지 않는다. 멀티 워커 전환 시에는
    BEGIN IMMEDIATE 트랜잭션 기반으로 재설계한다 (원칙 5 — 단일 프로세스 전제).
    """
    job = session.scalars(
        select(Job).where(Job.status == JobStatus.QUEUED).order_by(Job.id).limit(1)
    ).first()
    if job is None:
        return None
    job.status = JobStatus.RUNNING
    job.attempts = (job.attempts or 0) + 1
    job.started_at = datetime.now(timezone.utc)
    session.commit()
    return job


def run_job(ctx: JobContext, job: Job) -> Job:
    """클레임된 job을 실행한다 (동기 — 워커 스레드에서만 호출)."""
    session = ctx.session_factory()
    try:
        job = session.get(Job, job.id)
        try:
            handler = _HANDLERS[job.type]
            result = handler(ctx, session, job)
            session.expire(job)
            job = session.get(Job, job.id)
            job.status = JobStatus.DONE
            job.result = result
            job.finished_at = datetime.now(timezone.utc)
        except Exception as e:  # noqa: BLE001 — 작업 단위 실패는 job 상태로 기록
            session.rollback()
            job = session.get(Job, job.id)
            job.status = JobStatus.FAILED
            job.error_class = _classify(e)
            job.error = f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=4)}"
            job.finished_at = datetime.now(timezone.utc)
        session.commit()
        return job
    finally:
        session.close()


def _classify(e: Exception) -> JobErrorClass:
    from app.modules.plans.application.planrevise import PlanReviseError

    if isinstance(e, PlanError):
        return JobErrorClass.VALIDATION
    if isinstance(e, DeriveError):
        return JobErrorClass.LLM
    if isinstance(e, PlanReviseError):  # ValueError 상속 — ValueError 판정 전에
        return JobErrorClass.LLM
    if isinstance(e, ValueError):
        return JobErrorClass.SCHEMA
    mod = type(e).__module__ or ""
    if mod.startswith(("pptx", "docx")):
        return JobErrorClass.BUILDER
    return JobErrorClass.INTERNAL


# 핸들러 레지스트리 — 모듈 계층의 임포트 순환 여지가 없어 모듈 레벨 임포트로 충분하다
def _load_handlers() -> dict:
    from app.modules.derivatives.application.derive_build import run_derive_build
    from app.modules.plans.application.plan_revise_job import run_plan_revise_job
    from app.modules.review.application.run_review import run_review

    return {
        "derive_build": run_derive_build,
        "review": run_review,
        "plan_revise": run_plan_revise_job,
    }


_HANDLERS: dict = _load_handlers()


def requeue_stale_running(session_factory) -> int:
    """시작 시점에 running인 잡을 재큐잉한다 — 워커는 1개이므로, running 잡은
    직전 프로세스 비정상 종료의 잔재일 수밖에 없다 (orphan 방지)."""
    session = session_factory()
    try:
        n = session.execute(
            text("UPDATE jobs SET status='queued', started_at=NULL WHERE status='running'")
        ).rowcount
        session.commit()
        return n
    finally:
        session.close()


async def worker_loop(ctx: JobContext, poll_seconds: float = 1.0) -> None:
    """단일 백그라운드 워커 — lifespan이 시작/중단을 관리한다."""
    import asyncio
    import time

    import anyio

    requeued = requeue_stale_running(ctx.session_factory)
    if requeued:
        print(f"[worker] 이전 프로세스의 running 잡 {requeued}건 재큐잉", flush=True)

    while True:
        session = ctx.session_factory()
        try:
            job = claim_next_job(session)
        finally:
            session.close()
        if job is None:
            await asyncio.sleep(poll_seconds)
            continue
        # 진행 관측용 로그 — '고착인지 느린 실행인지'를 밖에서 판별 가능하게 한다.
        t0 = time.monotonic()
        print(f"[worker] job #{job.id} {job.type} 실행 (attempt {job.attempts})", flush=True)
        # 빌더·LLM은 블로킹 — 스레드로. 실행은 절대 병렬로 만들지 않는다.
        await anyio.to_thread.run_sync(run_job, ctx, job)
        print(f"[worker] job #{job.id} 종료 ({time.monotonic() - t0:.0f}s)", flush=True)