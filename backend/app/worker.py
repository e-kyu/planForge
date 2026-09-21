# -*- coding: utf-8 -*-
"""DB 기반 작업 큐 — 단일 워커 직렬 실행 (§3.1, 원칙 5).

- 빌드 동시성이 거의 없는 팀 단위 서비스(1~10명)라 Redis/Celery 없이 job 테이블 + 단일 워커.
- 빌더(build_ppt.BLANK_LAYOUT_IDX 모듈 전역)는 스레드 안전하지 않으므로
  **절대 병렬 실행 금지** — 워커 태스크가 1개이고 run_job은 단일 스레드에서 직렬 실행된다.
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from planforge.derive import DeriveError, Deriver
from planforge.plan import PlanError, parse_plan_file

from .agents.planrevise import PlanReviseError, run_plan_revise, validate_plan_markdown
from .models import (
    Build,
    Derivative,
    DerivativeKind,
    Fact,
    FactStatus,
    Job,
    JobErrorClass,
    JobStatus,
    Plan,
    PlanOrigin,
    PlanStatus,
    Project,
    ReviewReport,
)
from .workspace import atomic_build, parse_build_filename, write_plan_mirror


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
            from planforge.builders import build_ppt
            build_ppt.build(str(res.work_path), str(tmp))
    else:
        from planforge.builders import build_doc
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


# ---------------------------------------------------------------- review 핸들러 (FR-4)

def _review(ctx: JobContext, session: Session, job: Job) -> dict:
    """검수: 결정론(구조·수치·태그·팩트·세대) + LLM 내용 검수 → ReviewReport 1건."""
    import json as _json

    from planforge.numcheck import check_report, check_slides
    from planforge.plan import filter_slides, parse_plan_file
    from planforge.review import check_doc_tags, check_facts

    payload = job.payload
    project = session.get(Project, job.project_id)
    if project is None:
        raise ValueError("project가 없습니다")

    plan = session.get(Plan, payload["plan_id"])
    if plan is None:
        raise ValueError("plan이 없습니다")
    if plan.status != PlanStatus.APPROVED:
        raise PlanError("승인된 plan만 검수 대상입니다")

    findings: list[dict] = []

    def add(code: str, severity: str, where: str, message: str) -> None:
        findings.append({"code": code, "severity": severity, "where": where,
                         "message": message})

    # SSOT 미러 (Deriver와 동일 — 엔진이 읽는 파일 형태일 뿐)
    ws = Path(project.workspace_path)
    plan_mirror = write_plan_mirror(ws, plan.markdown)
    parsed = parse_plan_file(plan_mirror)

    # 1) 파생물 ↔ plan 대조 (구조 + 수치 무결성 — numcheck)
    # 같은 세대(plan_id 일치) 파생물만 — 이전 세대는 2)의 세대 대응성에서 보고한다
    derivative_docs: list[dict] = []
    derivs = session.scalars(
        select(Derivative).where(Derivative.project_id == project.id,
                                 Derivative.plan_id == plan.id)
    ).all()
    latest_by_key: dict[tuple, Derivative] = {}
    for d in derivs:
        latest_by_key[(d.kind, d.doc)] = d  # id 순 — 뒤(최신)가 이김
    for (kind, doc), d in sorted(latest_by_key.items()):
        derivative_docs.append({"doc": doc, "kind": kind.value, "json": d.json})
        slides = filter_slides(parsed.slides, doc)
        f = (check_slides(slides, parsed.key_messages, d.json) if kind == DerivativeKind.SLIDES
             else check_report(slides, parsed.key_messages, d.json))
        for x in f:
            add(x.code, x.severity, x.where, x.message)

    # 2) 세대 대응성 (FR-4.1) — 기존 빌드가 이 plan 세대인지 (채번은 확장자별 독립이므로 plan_id로)
    for b in session.scalars(
        select(Build).where(Build.project_id == project.id).order_by(Build.id)
    ).all():
        if b.plan_id != plan.id:
            add("generation", "red", f"산출물 {b.title}_v{b.version_no:02d}.{b.ext}",
                "이전 plan 세대의 산출물입니다 — plan을 고친 뒤 파생물을 재생성하세요 (재생성 대상)")

    # 3) 문서 태그 검수
    for x in check_doc_tags(parsed):
        add(x.code, x.severity, x.where, x.message)

    # 4) 팩트 대조 (FR-4.4 전제 — 활성 팩트만)
    facts = [{"content": f.content, "source": f.source, "date": f.date.isoformat()}
             for f in session.scalars(
                 select(Fact).where(Fact.project_id == project.id,
                                    Fact.status == FactStatus.ACTIVE)).all()]
    for x in check_facts(parsed, facts):
        add(x.code, x.severity, x.where, x.message)

    # 5) LLM 내용 검수 (실패해도 결정론 결과는 보존)
    llm_ok = True
    summary = ""
    try:
        from .agents.review import run_llm_review
        from .agents.llm import LLMRegistry
        registry = LLMRegistry(ctx.settings.llm_config_path, ctx.llm_overrides)
        lf, summary, llm_ok = run_llm_review(
            registry.chat_fn("review"), plan.markdown, derivative_docs, facts)
        findings.extend(lf)
    except Exception as e:  # noqa: BLE001 — 내용 검수 실패는 리포트를 막지 않는다
        llm_ok = False
        add("llm-review", "yellow", "내용 검수", f"LLM 내용 검수 실패: {e}")
    if not llm_ok and not any(f["code"] == "llm-review" for f in findings):
        add("llm-review", "yellow", "내용 검수",
            "LLM 내용 검수가 도구 호출 없이 종료됐습니다 — 결정론 검수 결과만 반영됨")

    counts = {"red": sum(1 for f in findings if f["severity"] == "red"),
              "yellow": sum(1 for f in findings if f["severity"] == "yellow"),
              "white": sum(1 for f in findings if f["severity"] == "white")}
    report = ReviewReport(
        project_id=project.id, plan_id=plan.id, findings=findings,
        red_count=counts["red"], yellow_count=counts["yellow"],
        white_count=counts["white"], llm_ok=llm_ok, summary=summary,
    )
    session.add(report)
    session.flush()
    return {"review_id": report.id, "counts": counts}


# ---------------------------------------------------------------- plan revise 핸들러 (FR-4.3)

def _plan_revise(ctx: JobContext, session: Session, job: Job) -> dict:
    """검수 발견사항 반영: LLM plan 수정 → 결정론 검증 → 새 DRAFT 세대 (FR-4.3).

    파생물·빌드는 건드리지 않는다 — plan 세대만 추가하고, 승인 게이트·재생성은
    기존 게이트(derive_build의 APPROVED 검사)를 그대로 경유한다 (SSOT, 원칙 5).
    """
    payload = job.payload
    plan = session.get(Plan, payload["plan_id"])
    project = session.get(Project, job.project_id)
    if plan is None or project is None:
        raise ValueError("plan 또는 project가 없습니다")
    review = session.get(ReviewReport, payload["review_id"])
    if review is None or review.project_id != job.project_id:
        raise ValueError("검수 리포트가 없습니다")
    if review.plan_id != plan.id:
        raise ValueError("검수 리포트의 plan 세대가 job payload와 다릅니다")

    findings = list(review.findings or [])
    indices = payload.get("finding_indices")
    if indices is None:
        selected = findings
    else:
        selected = [findings[i] for i in indices if 0 <= i < len(findings)]
    if not selected:
        raise PlanError("반영할 발견사항이 없습니다")

    from .agents.llm import LLMRegistry

    registry = LLMRegistry(ctx.settings.llm_config_path, ctx.llm_overrides)
    try:
        chat_fn = registry.chat_fn("plan_revise")
    except KeyError:
        chat_fn = registry.chat_fn("review")  # 신규 프로필이 없는 기존 config 호환
    md, parsed = run_plan_revise(chat_fn, plan.markdown, selected, review.summary or "")

    validate_plan_markdown(md)  # 이중 방어 — run_plan_revise 내부 검증과 동일 권위
    if md.strip() == (plan.markdown or "").strip():
        raise PlanError("LLM 결과에 변경이 없습니다 — plan 세대를 만들지 않았습니다")

    max_ver = session.scalar(
        select(Plan.version_no).where(Plan.project_id == plan.project_id)
        .order_by(Plan.version_no.desc()).limit(1)
    )
    new_plan = Plan(project_id=plan.project_id, version_no=(max_ver or 0) + 1,
                    markdown=md, docs=parsed.docs, parsed_ok=True,
                    status=PlanStatus.DRAFT, origin=PlanOrigin.REVIEW)
    session.add(new_plan)
    session.flush()
    # SSOT 미러 — revise_plan(api/plans.py)과 동일: DRAFT 세대도 미러를 갱신한다
    write_plan_mirror(Path(project.workspace_path), md)
    return {"plan_id": new_plan.id, "version_no": new_plan.version_no,
            "applied_count": len(selected)}


_HANDLERS = {"derive_build": _derive_build, "review": _review, "plan_revise": _plan_revise}


# ---------------------------------------------------------------- 워커 루프 (앱 lifespan용)

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