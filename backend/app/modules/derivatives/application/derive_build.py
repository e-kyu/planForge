# -*- coding: utf-8 -*-
"""derive_build job 핸들러 (FR-3) — 승인된 plan → 파생물 → 결정론 빌드·채번.

SSOT(원칙 1): DB plan 행을 plan.md 미러로 갱신한 뒤 Deriver가 파일을 읽는다.
빌더 로직은 건드리지 않고 원자적 실행(atomic_build)만 담당한다 (D7).
"""
from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path

from planforge.derive import Deriver
from planforge.plan import PlanError, parse_plan_file

from app.modules.plans.facade import PlanStatus, get_plan
from app.modules.projects.facade import get_project
from app.shared.workspace import atomic_build, parse_build_filename, write_plan_mirror

from ..infrastructure.models import Build, Derivative, DerivativeKind


def run_derive_build(ctx, session, job) -> dict:
    payload = job.payload
    plan = get_plan(session, payload["plan_id"])
    project = get_project(session, job.project_id)
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

    from app.modules.jobs.facade import report_progress
    from app.shared.llm import LLMRegistry

    def progress(step: str, **kw) -> None:
        # 진행 기록 — DB 오류가 작업 자체를 죽이지 않게 방어한다 (facade 계약: caller 방어).
        try:
            report_progress(session, job, step, **kw)
        except Exception:
            print(f"[derive] job #{job.id} 진행 기록 실패", flush=True)

    def on_attempt(n: int, max_n: int) -> None:
        progress("llm", attempt=n, max_attempts=max_n)

    registry = LLMRegistry(ctx.settings.llm_config_path, ctx.llm_overrides)
    deriver = Deriver(registry.chat_fn("derive"), ws)
    # 진행 기록 불변식 — 모든 report_progress는 대기 중 도메인 행이 없는 시점에서만 호출한다.
    # report_progress가 세션 전체를 커밋하므로(facade 계약), 조기 커밋은 빌드 실패 시 고아
    # Derivative를 남긴다. 그래서 session.add()는 전부 atomic_build 이후로 밀렸다.
    t_llm = time.monotonic()
    print(f"[derive] job #{job.id} LLM 변환 시작 (kind={kind}, doc={doc})", flush=True)
    progress("llm")
    res = deriver.derive(plan_mirror, kind, doc, on_attempt=on_attempt)
    print(f"[derive] job #{job.id} LLM 변환 완료 "
          f"({time.monotonic() - t_llm:.0f}s, attempts={res.attempts})", flush=True)
    progress("build")

    # 결정론 빌드 — 원자적 실행 (D7). 빌더 로직은 건드리지 않는다.
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
    made = atomic_build(ws, run_builder)
    print(f"[derive] job #{job.id} 결정론 빌드 완료 "
          f"({time.monotonic() - t_build:.0f}s, 파일 {len(made)}건)", flush=True)

    # 도메인 행 생성 — 여기부터는 report_progress를 호출하지 않는다 (진행 기록 불변식).
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

    # 결정 17 — 수치 판정은 검수 단계. red 잔여면 같은 커밋에 검수 잡을 큐에 넣는다.
    # 모든 report_progress가 끝난 뒤이므로 "진행 기록 불변식(대기 중 도메인 행 0)" 유지.
    from planforge.numcheck import has_red

    if has_red(res.findings):
        from app.modules.review.facade import enqueue_auto_review

        if enqueue_auto_review(session, project.id, plan.id):
            print(f"[derive] job #{job.id} 잔여 수치 위반 — 검수 자동 큐진입", flush=True)

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


def _read_json(path: Path) -> dict:
    import json
    return json.loads(path.read_text(encoding="utf-8"))