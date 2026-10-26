# -*- coding: utf-8 -*-
"""derive_build job 핸들러 (FR-3) — 승인된 plan → 파생물 → 결정론 빌드·채번.

SSOT(원칙 1): DB plan 행을 plan.md 미러로 갱신한 뒤 Deriver가 파일을 읽는다.
빌더 로직은 건드리지 않고 원자적 실행(atomic_build)만 담당한다 (D7).

단일 책임 분해: 컨텍스트 로드 → 워크스페이스 해석 → LLM 변환 → 결정론 빌드 →
도메인 행 영속 → 자동 검수 큐잉 → 결과 조립. 진행 기록(report_progress)은 세션
전체를 커밋하므로 **모든 session.add는 atomic_build 이후**라는 불변식을 유지한다
(결정 15 — 빌드 실패 시 고아 Derivative 0건, output 무손상).
"""
from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path

from planforge.common.io import read_json
from planforge.derive import Deriver
from planforge.plan import PlanError

from app.modules.docloops import facade as docloops
from app.modules.jobs.facade import report_progress_safe
from app.modules.plans.facade import PlanStatus, get_plan
from app.modules.projects.facade import get_project
from app.shared.workspace import (
    atomic_build,
    ensure_doc_ws,
    parse_build_filename,
    write_plan_mirror,
)

from ..infrastructure.models import Build, Derivative, DerivativeKind


def run_derive_build(ctx, session, job) -> dict:
    plan, project = _load_job_context(session, job)

    kind = job.payload["kind"]
    doc = job.payload.get("doc")
    fmts = tuple(job.payload.get("fmts") or ())

    ws_root = _resolve_workspace(plan, project, session)
    # SSOT: DB plan 행을 plan.md 미러로 갱신 (idempotent — Deriver가 파일을 읽음)
    plan_mirror = write_plan_mirror(ws_root, plan.markdown)

    res = _run_llm_phase(ctx, session, job, ws_root, plan_mirror, kind, doc)
    made = _run_build_phase(session, job, ws_root, res, kind, fmts)
    derivative, builds = _persist_rows(session, job, plan, project, kind, res, made)
    _maybe_enqueue_review(session, job, project, plan, res)
    return _job_result(derivative, builds, res)


def _load_job_context(session, job) -> tuple:
    """plan/project 조회 + 승인 게이트(§FR-2.9) — 큐 진입과 실행 사이 상태 변경 방지."""
    plan = get_plan(session, job.payload["plan_id"])
    project = get_project(session, job.project_id)
    if plan is None or project is None:
        raise ValueError("plan 또는 project가 없습니다")
    if plan.status != PlanStatus.APPROVED:
        raise PlanError("승인되지 않은 plan으로는 파생물을 생성할 수 없습니다")
    return plan, project


def _resolve_workspace(plan, project, session) -> Path:
    """문서별 워크스페이스 루트 — 경로 권위는 plan.doc_slug, 레이아웃 권위는 doc_loops 행.

    레거시(행 없음 · doc_slug=None)는 프로젝트 루트를 유지한다 (step 1 doc_ws_root 계약).
    직접 시드 승인 plan 등 하위 구조가 없을 수 있는 경로만 멱등 생성한다.
    """
    ws = Path(project.workspace_path)
    root = docloops.resolve_workspace_root(session, project.id, ws, plan.doc_slug)
    if root != ws:
        ensure_doc_ws(root)
    return root


def _run_llm_phase(ctx, session, job, ws_root: Path, plan_mirror: Path,
                   kind: str, doc: str | None):
    """LLM 변환 — 진행 기록은 대기 중 도메인 행이 없는 이 시점에만 호출한다."""
    from app.shared.llm import LLMRegistry

    def progress(step: str, **kw) -> None:
        report_progress_safe(session, job, step, log_tag="derive", **kw)

    def on_attempt(n: int, max_n: int) -> None:
        progress("llm", attempt=n, max_attempts=max_n)

    registry = LLMRegistry(ctx.settings.llm_config_path, ctx.llm_overrides)
    deriver = Deriver(registry.chat_fn("derive"), ws_root)
    t_llm = time.monotonic()
    print(f"[derive] job #{job.id} LLM 변환 시작 (kind={kind}, doc={doc})", flush=True)
    progress("llm")
    res = deriver.derive(plan_mirror, kind, doc, on_attempt=on_attempt)
    print(f"[derive] job #{job.id} LLM 변환 완료 "
          f"({time.monotonic() - t_llm:.0f}s, attempts={res.attempts})", flush=True)
    return res


def _run_build_phase(session, job, ws_root: Path, res, kind: str, fmts: tuple) -> list[Path]:
    """결정론 빌드 — 원자적 실행 (D7). 빌더 로직은 건드리지 않는다."""
    def progress(step: str, **kw) -> None:
        report_progress_safe(session, job, step, log_tag="derive", **kw)

    progress("build")
    if kind == "slides":
        def run_builder(tmp: Path):
            progress("build", detail="PPTX 작성 중")
            from planforge.builders import build_ppt
            build_ppt.build(str(res.work_path), str(tmp))
    else:
        from planforge.builders import build_doc
        def run_builder(tmp: Path):
            for fmt in (fmts or ("md", "html", "docx")):
                progress("build", detail=f"{fmt.upper()} 작성 중")
                build_doc.build(str(res.work_path), fmt, str(tmp))

    t_build = time.monotonic()
    made = atomic_build(ws_root, run_builder)
    print(f"[derive] job #{job.id} 결정론 빌드 완료 "
          f"({time.monotonic() - t_build:.0f}s, 파일 {len(made)}건)", flush=True)
    return made


def _persist_rows(session, job, plan, project, kind: str, res, made: list[Path]):
    """도메인 행 생성 — 여기부터는 report_progress를 호출하지 않는다 (진행 기록 불변식).

    대상 문서는 Deriver가 로더로 해석한 값(res.doc, doc=None → plan.docs[0])을 그대로
    쓴다 — 같은 plan을 다시 파싱하지 않는다.
    """
    resolved_doc = res.doc
    derivative = Derivative(
        plan_id=plan.id,
        project_id=project.id,
        kind=DerivativeKind(kind),
        doc=resolved_doc,
        json=read_json(res.work_path),
        slides_count=res.slides_count,
        sections_count=res.sections_count,
        unconfirmed=res.unconfirmed or None,
        attempts=res.attempts,
    )
    session.add(derivative)
    session.flush()

    builds = []
    for f in made:
        parsed = parse_build_filename(f.name)
        if parsed is None:
            continue
        title, version_no, ext = parsed
        builds.append(Build(
            project_id=project.id,
            plan_id=plan.id,
            doc_slug=plan.doc_slug,
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
    return derivative, builds


def _maybe_enqueue_review(session, job, project, plan, res) -> None:
    """결정 17 — 수치 판정은 검수 단계. red 잔여면 같은 커밋에 검수 잡을 큐에 넣는다.

    모든 report_progress가 끝난 뒤이므로 "진행 기록 불변식(대기 중 도메인 행 0)" 유지.
    """
    from planforge.numcheck import has_red

    if has_red(res.findings):
        from app.modules.review.facade import enqueue_auto_review

        if enqueue_auto_review(session, project.id, plan.id):
            print(f"[derive] job #{job.id} 잔여 수치 위반 — 검수 자동 큐진입", flush=True)


def _job_result(derivative, builds, res) -> dict:
    """job.result 조립 — 키·값·순서 불변 (JobOut.result는 free-form dict)."""
    result = {
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
    if res.findings:
        # numcheck 측정값 — Finding dict는 run_review 발견사항과 동형 (코드/severity/위치/메시지)
        result["findings"] = [asdict(f) for f in res.findings]
    return result
