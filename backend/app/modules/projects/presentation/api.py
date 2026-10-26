# -*- coding: utf-8 -*-
"""프로젝트 관리 API (FR-1)."""
from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.docloops.facade import DOC_KINDS, DocLoop, list_loops
from app.modules.docloops.presentation.schemas import DocLoopOut
from app.modules.plans.facade import (
    latest_generations_by_doc,
    latest_generations_by_project_doc,
)
from app.shared.config import Settings, get_settings
from app.shared.db import get_db
from app.shared.errors import http_404

from ..application import service
from ..infrastructure.models import Project, ProjectStatus
from .schemas import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _docloops_single(db: Session, project_id: int) -> list[DocLoopOut]:
    """단건 응답용 — docloops facade의 정렬된 list_loops 경유 (쿼리 2회)."""
    latest = latest_generations_by_doc(db, project_id)
    return [DocLoopOut.from_row(r, latest.get(r.doc_slug))
            for r in list_loops(db, project_id)]


def _docloops_batch(db: Session, project_ids: list[int]) -> dict[int, list[DocLoopOut]]:
    """목록 응답용 배치 로드 — 루프 행 1회 + plans 최신 세대 1회 조회로 N+1 방지.

    정렬은 list_loops와 같은 DOC_KINDS 순서(매핑에 없는 slug는 뒤로)를 유지한다.
    """
    out: dict[int, list[DocLoopOut]] = {pid: [] for pid in project_ids}
    if not project_ids:
        return out
    order = {slug: i for i, (slug, _) in enumerate(DOC_KINDS)}
    rows = db.scalars(select(DocLoop).where(DocLoop.project_id.in_(project_ids))).all()
    latest = latest_generations_by_project_doc(db, project_ids)
    for r in sorted(rows, key=lambda r: (r.project_id,
                                         order.get(r.doc_slug, len(order)),
                                         r.doc_slug)):
        out[r.project_id].append(DocLoopOut.from_row(
            r, latest.get((r.project_id, r.doc_slug))))
    return out


def _project_out(p: Project, db: Session) -> ProjectOut:
    out = ProjectOut.model_validate(p)
    out.docloops = _docloops_single(db, p.id)
    return out


def _projects_out(projects: list[Project], db: Session) -> list[ProjectOut]:
    loops = _docloops_batch(db, [p.id for p in projects])
    outs = []
    for p in projects:
        out = ProjectOut.model_validate(p)
        out.docloops = loops.get(p.id, [])
        outs.append(out)
    return outs


@router.post("", status_code=201, response_model=ProjectOut)
def create_project(body: ProjectCreate, db: Session = Depends(get_db),
                   settings: Settings = Depends(get_settings)):
    p = service.create_project(db, settings, body.slug, body.title, body.owner)
    return _project_out(p, db)


@router.get("", response_model=list[ProjectOut])
def list_projects(status: str | None = Query(default=None),
                  db: Session = Depends(get_db)):
    q = select(Project).order_by(Project.id)
    if status:
        q = q.where(Project.status == ProjectStatus(status))
    return _projects_out(list(db.scalars(q)), db)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if p is None:
        raise http_404(f"프로젝트 없음: {project_id}")
    return _project_out(p, db)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if p is None:
        raise http_404(f"프로젝트 없음: {project_id}")
    if body.title is not None:
        p.title = body.title
    if body.status is not None:
        p.status = ProjectStatus(body.status)
    return _project_out(p, db)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    """프로젝트 하드 삭제 — 추적성 사슬(§5) 전체 + 워크스페이스 디렉토리를 함께 제거한다.

    대기/실행 중 job이 있으면 409로 막는다(단일 워커 직렬 전제 — 실행 도중
    프로젝트가 사라지는 것 방지). 자식 → 부모 순서로 삭제하며(SQLite FK ON),
    파일 삭제는 DB 커밋 후 수행한다(파일보다 레코드가 권위).
    """
    p = service.delete_project(db, project_id)
    db.commit()
    shutil.rmtree(p.workspace_path, ignore_errors=True)