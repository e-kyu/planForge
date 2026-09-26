# -*- coding: utf-8 -*-
"""파생물 생성·빌드 API (FR-3) — 승인된 plan에서만 큐 진입."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.jobs.facade import JobType, enqueue
from app.modules.jobs.presentation.schemas import JobOut
from app.modules.plans.facade import latest_approved
from app.modules.projects.facade import require_project
from app.shared.config import Settings, get_settings
from app.shared.db import get_db
from app.shared.errors import http_404, http_409
from app.shared.workspace import ensure_workspace_dirs

from ..infrastructure.models import Build, Derivative
from .schemas import BuildOut, DerivativeCreate, DerivativeOut

router = APIRouter(prefix="/api/projects/{project_id}", tags=["derivatives"])


@router.post("/derivatives", status_code=202, response_model=JobOut)
def enqueue_derivative(project_id: int, body: DerivativeCreate,
                       db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    project = require_project(db, project_id)
    if body.kind not in ("slides", "report"):
        raise http_409("kind는 slides|report 중 하나여야 합니다")
    if body.fmts is not None:
        bad = [f for f in body.fmts if f not in ("md", "html", "docx")]
        if bad:
            raise http_409(f"지원하지 않는 포맷: {bad}")

    # FR-2.9 승인 게이트 — 최신 승인 plan이 대상 (승인본 없으면 409)
    plan = latest_approved(db, project_id)
    if plan is None:
        raise http_409("승인된 plan이 없습니다 — 먼저 plan을 승인하세요")

    ensure_workspace_dirs(Path(project.workspace_path))
    job = enqueue(db, project_id, JobType.DERIVE_BUILD,
                  {"plan_id": plan.id, "kind": body.kind, "doc": body.doc,
                   "fmts": body.fmts})
    return JobOut.model_validate(job)


@router.get("/derivatives", response_model=list[DerivativeOut])
def list_derivatives(project_id: int, plan_id: int | None = None,
                     db: Session = Depends(get_db)):
    q = select(Derivative).where(Derivative.project_id == project_id).order_by(Derivative.id)
    if plan_id is not None:
        q = q.where(Derivative.plan_id == plan_id)
    return [DerivativeOut.model_validate(d) for d in db.scalars(q)]


@router.get("/outputs", response_model=list[BuildOut])
def list_outputs(project_id: int, db: Session = Depends(get_db),
                 settings: Settings = Depends(get_settings)):
    project = require_project(db, project_id)
    out = []
    for b in db.scalars(
        select(Build).where(Build.project_id == project_id).order_by(Build.id.desc())
    ):
        item = BuildOut.model_validate(b)
        # fs 존재 재확인 — 파일이 지워졌으면 노출하지 않는다
        if (Path(project.workspace_path) / b.file_path).is_file():
            out.append(item)
    return out


@router.get("/outputs/{build_id}/download")
def download_output(project_id: int, build_id: int, db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse

    b = db.get(Build, build_id)
    if b is None or b.project_id != project_id:
        raise http_404(f"산출물 없음: {build_id}")
    project = require_project(db, project_id)
    full = Path(project.workspace_path) / b.file_path
    if not full.is_file():
        raise http_404("파일이 워크스페이스에 없습니다")
    media = {"md": "text/markdown", "html": "text/html"}.get(b.ext)
    inline = media is not None
    return FileResponse(
        full,
        media_type=media or "application/octet-stream",
        filename=b.title + "_v" + f"{b.version_no:02d}." + b.ext,
        content_disposition_type="inline" if inline else "attachment",
    )