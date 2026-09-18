# -*- coding: utf-8 -*-
"""팩트 저장소 API (원칙 4) — 인터뷰 확립 팩트 + 수동 팩트."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..errors import http_404
from ..models import Fact, FactOrigin, FactStatus, Project
from ..workspace import compact_interview_log, workspace_path

router = APIRouter(prefix="/api/projects/{project_id}/facts", tags=["facts"])


class FactCreate(BaseModel):
    content: str
    source: str = ""
    date: dt.date | None = None
    origin: str = "manual"


class FactUpdate(BaseModel):
    content: str | None = None
    source: str | None = None
    status: str | None = None  # active | archived (FR-6.1 압축 대비)


class FactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    session_id: int | None
    date: dt.date
    content: str
    source: str
    status: str
    origin: str
    created_at: object


@router.get("", response_model=list[FactOut])
def list_facts(project_id: int, status: str | None = None, db: Session = Depends(get_db)):
    q = select(Fact).where(Fact.project_id == project_id).order_by(Fact.id)
    if status:
        q = q.where(Fact.status == FactStatus(status))
    return [FactOut.model_validate(f) for f in db.scalars(q)]


@router.post("", status_code=201, response_model=FactOut)
def create_fact(project_id: int, body: FactCreate, db: Session = Depends(get_db)):
    if db.get(Project, project_id) is None:
        raise http_404(f"프로젝트 없음: {project_id}")
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

UNCONFIRMED = "(미확정)"


class CompactGroup(BaseModel):
    topic: str = ""
    keep_id: int
    archive_ids: list[int] = []
    reason: str = ""


class CompactPreview(BaseModel):
    ok: bool
    summary: str = ""
    warning: str | None = None
    groups: list[CompactGroup]
    facts: list[FactOut]  # 활성 팩트 전체 (프론트 표시용)


class CompactApplyRequest(BaseModel):
    groups: list[CompactGroup]


class CompactApplyResult(BaseModel):
    archived: list[int]
    active_remaining: int
    log_path: str
    archive_path: str
    warnings: list[str]


def _clean_groups(groups: list[dict], facts: list[Fact]) -> list[CompactGroup]:
    """LLM 제안을 결정론 검증·정화한다 — 존재하지 않는 id·(미확정) 항목 archive 금지."""
    by_id = {f.id: f for f in facts}
    cleaned: list[CompactGroup] = []
    for g in groups:
        keep = g.get("keep_id")
        if keep not in by_id:
            continue
        archives: list[int] = []
        for aid in sorted({a for a in g.get("archive_ids", []) if isinstance(a, int)}):
            f = by_id.get(aid)
            if f is None or aid == keep or UNCONFIRMED in f.content:
                continue  # (미확정) 항목은 활성 유지 (legacy 주의 절 — 결정론 강제)
            archives.append(aid)
        if archives:
            cleaned.append(CompactGroup(topic=str(g.get("topic", "")), keep_id=keep,
                                        archive_ids=archives, reason=str(g.get("reason", ""))))
    return cleaned


def _fact_line(f: Fact, marker: str = "") -> str:
    """interview-log 항목 형식 — 날짜·출처 표기 형식은 legacy 규약 유지."""
    line = f"[{f.date.isoformat()}] {f.content} (출처: {f.source})"
    return f"{line} {marker}".strip() if marker else line


@router.post("/compact", response_model=CompactPreview)
def compact_preview(project_id: int, request: Request, db: Session = Depends(get_db),
                    settings=Depends(get_settings)):
    """LLM 통합 그룹 제안 (게이트 1단 — 승인 전까지는 아무 것도 바꾸지 않는다)."""
    if db.get(Project, project_id) is None:
        raise http_404(f"프로젝트 없음: {project_id}")
    facts = db.scalars(
        select(Fact).where(Fact.project_id == project_id,
                           Fact.status == FactStatus.ACTIVE).order_by(Fact.id)).all()
    out_facts = [FactOut.model_validate(f) for f in facts]
    if len(facts) < 2:
        return CompactPreview(ok=True, summary="활성 팩트가 1개 이하라 압축 대상이 없습니다",
                              groups=[], facts=out_facts)

    from ..agents.compact import run_llm_compact
    from ..agents.llm import LLMRegistry

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
                          groups=_clean_groups(groups, facts), facts=out_facts)


@router.post("/compact/apply", response_model=CompactApplyResult)
def compact_apply(project_id: int, body: CompactApplyRequest, db: Session = Depends(get_db),
                  settings=Depends(get_settings)):
    """승인된 그룹의 이전 팩트를 archive로 + interview-log 미러 재작성 (게이트 2단)."""
    project = db.get(Project, project_id)
    if project is None:
        raise http_404(f"프로젝트 없음: {project_id}")
    facts = db.scalars(
        select(Fact).where(Fact.project_id == project_id,
                           Fact.status == FactStatus.ACTIVE).order_by(Fact.id)).all()
    by_id = {f.id: f for f in facts}

    warnings: list[str] = []
    to_archive: dict[int, Fact] = {}
    for g in body.groups:
        if g.keep_id not in by_id:
            warnings.append(f"그룹 '{g.topic}': keep #{g.keep_id}가 활성 팩트가 아닙니다 — 건너뜀")
            continue
        for aid in g.archive_ids:
            if aid == g.keep_id:
                continue
            f = by_id.get(aid)
            if f is None:
                continue
            if UNCONFIRMED in f.content:
                warnings.append(f"팩트 #{aid}는 (미확정) 항목이라 archive하지 않았습니다")
                continue
            to_archive[aid] = f

    for f in to_archive.values():
        f.status = FactStatus.ARCHIVED

    remaining = [f for f in facts if f.id not in to_archive]
    today = dt.date.today().isoformat()
    active_lines = [_fact_line(f) for f in remaining]
    archived_lines = [_fact_line(f, marker=f"[archive: {today}]") for f in to_archive.values()]
    log, arch = compact_interview_log(workspace_path(settings, project.slug),
                                      active_lines, archived_lines)
    db.commit()
    return CompactApplyResult(
        archived=sorted(to_archive), active_remaining=len(remaining),
        log_path=str(log), archive_path=str(arch), warnings=warnings)