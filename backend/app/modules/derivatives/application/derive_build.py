# -*- coding: utf-8 -*-
"""derive_build job 핸들러 (FR-3) — 승인된 plan → 파생물 → 결정론 빌드·채번.

SSOT(원칙 1): DB plan 행을 plan.md 미러로 갱신한 뒤 Deriver가 파일을 읽는다.
빌더 로직은 건드리지 않고 원자적 실행(atomic_build)만 담당한다 (D7).
"""
from __future__ import annotations

import time
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

    from app.shared.llm import LLMRegistry

    registry = LLMRegistry(ctx.settings.llm_config_path, ctx.llm_overrides)
    deriver = Deriver(registry.chat_fn("derive"), ws)
    # 단계별 경계 로그 — 잡 시간을 LLM 변환 vs 결정론 빌드로 분해해 관측한다.
    t_llm = time.monotonic()
    print(f"[derive] job #{job.id} LLM 변환 시작 (kind={kind}, doc={doc})", flush=True)
    res = deriver.derive(plan_mirror, kind, doc)
    print(f"[derive] job #{job.id} LLM 변환 완료 "
          f"({time.monotonic() - t_llm:.0f}s, attempts={res.attempts})", flush=True)
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

    t_build = time.monotonic()
    made = atomic_build(ws, run_builder)
    print(f"[derive] job #{job.id} 결정론 빌드 완료 "
          f"({time.monotonic() - t_build:.0f}s, 파일 {len(made)}건)", flush=True)

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