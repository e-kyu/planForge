# -*- coding: utf-8 -*-
"""DB 기반 작업 큐 — 단일 워커 직렬 실행 (§3.1, 원칙 5).

- 빌드 동시성이 거의 없는 팀 단위 서비스(1~10명)라 Redis/Celery 없이 job 테이블 + 단일 워커.
- 빌더(build_ppt.BLANK_LAYOUT_IDX 모듈 전역)는 스레드 안전하지 않으므로
  **절대 병렬 실행 금지** — claim이 FOR UPDATE SKIP LOCKED 단건이고 워커 태스크도 1개다.
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from reportagent.derive import DeriveError, Deriver
from reportagent.plan import PlanError, parse_plan_file

from .models import (
    Build,
    Derivative,
    DerivativeKind,
    Job,
    JobErrorClass,
    JobStatus,
    Plan,
    PlanStatus,
    Project,
)
from .workspace import atomic_build, parse_build_filename, write_plan_mirror


@dataclass
class JobContext:
    """run_job 실행 컨텍스트 — 테스트에서 LLM을 주입하려면 llm_overrides를 쓴다."""

    session_factory: sessionmaker
    settings: object
    llm_overrides: dict | None = None


def claim_next_job(session: Session) -> Job | None:
    """큐에서 다음 job을 원자적으로 클레임한다 (동시 워커 대비 방어 — 현재는 워커 1개)."""
    job_id = session.execute(
        text(
            "SELECT id FROM jobs WHERE status = 'queued' "
            "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1"
        )
    ).scalar()
    if job_id is None:
        return None
    job = session.get(Job, job_id)
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
    if isinstance(e, PlanError):
        return JobErrorClass.VALIDATION
    if isinstance(e, DeriveError):
        return JobErrorClass.LLM
    if isinstance(e, ValueError):
        return JobErrorClass.SCHEMA
    mod = type(e).__module__ or ""
    if mod.startswith(("pptx", "docx")):
        return JobErrorClass.BUILDER
    return JobErrorClass.INTERNAL


# ---------------------------------------------------------------- derive_build 핸들러

def _derive_build(ctx: JobContext, session: Session, job: Job) -> dict:
    payload = job.payload
    plan = session.get(Plan, payload["plan_id"])
    project = session.get(Project, job.project_id)
    if plan is None or project is None:
        raise ValueError("plan 또는 project가 없습니다")
    if plan.status != PlanStatus.APPROVED:
        # 승인 게이트(§FR-2.9) — 큐 진입 시점과 실행 시점 사이 상태 변경 방지
        raise PlanError("승인되지 않은 plan으로는 파생물을 생성할 수 없습니다")

    ws = Path(project.workspace_path)
    kind = payload["kind"]
    doc = payload.get("doc")
    fmts = tuple(payload.get("fmts") or ())

    # SSOT: DB plan 행을 plan.md 미러로 갱신 (idempotent — Deriver가 파일을 읽음)
    plan_mirror = write_plan_mirror(ws, plan.markdown)

    from .agents.llm import LLMRegistry

    registry = LLMRegistry(ctx.settings.llm_config_path, ctx.llm_overrides)
    deriver = Deriver(registry.chat_fn("derive"), ws)
    res = deriver.derive(plan_mirror, kind, doc)
    # Deriver가 기본 문서를 해석했다 (doc=None → plan.docs[0])
    resolved_doc = doc or parse_plan_file(plan_mirror).docs[0]

    derivative = Derivative(
        plan_id=plan.id,
        project_id=project.id,
        kind=DerivativeKind(kind),
        doc=resolved_doc,
        json=_read_json(res.work_path),
        slides_count=res.slides_count,
        sections_count=res.sections_count,
        unconfirmed=res.unconfirmed or None,
        attempts=res.attempts,
    )
    session.add(derivative)
    session.flush()

    # 결정론 빌드 — 원자적 실행 (D7). 빌더 로직은 건드리지 않는다.
    if kind == "slides":
        def run_builder(tmp: Path):
            from reportagent.builders import build_ppt
            build_ppt.build(str(res.work_path), str(tmp))
    else:
        from reportagent.builders import build_doc
        def run_builder(tmp: Path):
            for fmt in (fmts or ("md", "html", "docx")):
                build_doc.build(str(res.work_path), fmt, str(tmp))

    made = atomic_build(ws, run_builder)

    builds = []
    for f in made:
        parsed = parse_build_filename(f.name)
        if parsed is None:
            continue
        title, version_no, ext = parsed
        builds.append(Build(
            project_id=project.id,
            plan_id=plan.id,
            derivative_id=derivative.id,
            job_id=job.id,
            doc_kind=resolved_doc,
            ext=ext,
            version_no=version_no,
            title=title,
            file_path=f"output/{f.name}",
            size_bytes=f.stat().st_size,
        ))
    session.add_all(builds)
    session.flush()

    return {
        "derivative_id": derivative.id,
        "builds": [
            {"build_id": b.id, "file_path": b.file_path, "version_no": b.version_no, "ext": b.ext}
            for b in builds
        ],
        "counts": {
            "slides": derivative.slides_count,
            "sections": derivative.sections_count,
            "attempts": derivative.attempts,
        },
    }


def _read_json(path: Path) -> dict:
    import json
    return json.loads(path.read_text(encoding="utf-8"))


_HANDLERS = {"derive_build": _derive_build}


# ---------------------------------------------------------------- 워커 루프 (앱 lifespan용)

async def worker_loop(ctx: JobContext, poll_seconds: float = 1.0) -> None:
    """단일 백그라운드 워커 — lifespan이 시작/중단을 관리한다."""
    import asyncio

    import anyio

    while True:
        session = ctx.session_factory()
        try:
            job = claim_next_job(session)
        finally:
            session.close()
        if job is None:
            await asyncio.sleep(poll_seconds)
            continue
        # 빌더·LLM은 블로킹 — 스레드로. 실행은 절대 병렬로 만들지 않는다.
        await anyio.to_thread.run_sync(run_job, ctx, job)