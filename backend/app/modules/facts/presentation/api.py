# -*- coding: utf-8 -*-
"""팩트 저장소 API (원칙 4) — 인터뷰 확립 팩트 + 수동 팩트."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.projects.facade import require_project
from app.shared.config import get_settings
from app.shared.db import get_db
from app.shared.errors import http_404
from app.shared.llm import LLMRegistry
from app.shared.workspace import compact_interview_log, workspace_path

from ..application.compact import clean_groups, fact_line, run_llm_compact, select_archives
from ..facade import FactStatus
from ..infrastructure.models import Fact, FactOrigin
from .schemas import (
    CompactApplyRequest,
    CompactApplyResult,
    CompactGroup,
    CompactPreview,
    FactCreate,
    FactOut,
    FactUpdate,
)

router = APIRouter(prefix="/api/projects/{project_id}/facts", tags=["facts"])


@router.get("", response_model=list[FactOut])
def list_facts(project_id: int, status: str | None = None, db: Session = Depends(get_db)):
    q = select(Fact).where(Fact.project_id == project_id).order_by(Fact.id)
    if status:
        q = q.where(Fact.status == FactStatus(status))
    return [FactOut.model_validate(f) for f in db.scalars(q)]


@router.post("", status_code=201, response_model=FactOut)
def create_fact(project_id: int, body: FactCreate, db: Session = Depends(get_db)):
    require_project(db, project_id)
    f = Fact(project_id=project_id, content=body.content, source=body.source,
             date=body.date or dt.date.today(), origin=FactOrigin(body.origin))
    db.add(f)
    db.flush()
    return FactOut.model_validate(f)


@router.patch("/{fact_id}", response_model=FactOut)
def update_fact(project_id: int, fact_id: int, body: FactUpdate, db: Session = Depends(get_db)):
    f = db.get(Fact, fact_id)
    if f is None or f.project_id != project_id:
        raise http_404(f"팩트 없음: {fact_id}")
    if body.content is not None:
        f.content = body.content
    if body.source is not None:
        f.source = body.source
    if body.status is not None:
        f.status = FactStatus(body.status)
    return FactOut.model_validate(f)


# ---------------------------------------------------------------- 압축 (FR-6.1, compact-log 이식)

@router.post("/compact", response_model=CompactPreview)
def compact_preview(project_id: int, request: Request, db: Session = Depends(get_db),
                    settings=Depends(get_settings)):
    """LLM 통합 그룹 제안 (게이트 1단 — 승인 전까지는 아무 것도 바꾸지 않는다)."""
    require_project(db, project_id)
    facts = db.scalars(
        select(Fact).where(Fact.project_id == project_id,
                           Fact.status == FactStatus.ACTIVE).order_by(Fact.id)).all()
    out_facts = [FactOut.model_validate(f) for f in facts]
    if len(facts) < 2:
        return CompactPreview(ok=True, summary="활성 팩트가 1개 이하라 압축 대상이 없습니다",
                              groups=[], facts=out_facts)

    registry = LLMRegistry(settings.llm_config_path, request.app.state.llm_overrides)
    payload = [{"id": f.id, "date": f.date.isoformat(), "content": f.content, "source": f.source}
               for f in facts]
    try:
        groups, summary, ok = run_llm_compact(registry.chat_fn("derive"), payload)
        warning = None if ok else "LLM 압축 제안 실패 — 팩트는 변경되지 않았습니다"
    except Exception as e:  # noqa: BLE001 — 제안 실패는 무손실 (미적용)
        groups, summary, ok = [], "", False
        warning = f"LLM 압축 제안 실패: {e} — 팩트는 변경되지 않았습니다"
    return CompactPreview(ok=ok, summary=summary, warning=warning,
                          groups=[CompactGroup(**g) for g in clean_groups(groups, facts)],
                          facts=out_facts)


@router.post("/compact/apply", response_model=CompactApplyResult)
def compact_apply(project_id: int, body: CompactApplyRequest, db: Session = Depends(get_db),
                  settings=Depends(get_settings)):
    """승인된 그룹의 이전 팩트를 archive로 + interview-log 미러 재작성 (게이트 2단)."""
    project = require_project(db, project_id)
    facts = db.scalars(
        select(Fact).where(Fact.project_id == project_id,
                           Fact.status == FactStatus.ACTIVE).order_by(Fact.id)).all()

    to_archive, warnings = select_archives(facts, body.groups)
    for f in to_archive.values():
        f.status = FactStatus.ARCHIVED

    remaining = [f for f in facts if f.id not in to_archive]
    today = dt.date.today().isoformat()
    active_lines = [fact_line(f) for f in remaining]
    archived_lines = [fact_line(f, marker=f"[archive: {today}]") for f in to_archive.values()]
    log, arch = compact_interview_log(workspace_path(settings, project.slug),
                                      active_lines, archived_lines)
    db.commit()
    return CompactApplyResult(
        archived=sorted(to_archive), active_remaining=len(remaining),
        log_path=str(log), archive_path=str(arch), warnings=warnings)