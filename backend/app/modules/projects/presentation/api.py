# -*- coding: utf-8 -*-
"""프로젝트 관리 API (FR-1)."""
from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.shared.config import Settings, get_settings
from app.shared.db import get_db
from app.shared.errors import http_404

from ..application import service
from ..infrastructure.models import Project, ProjectStatus
from .schemas import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _project_out(p: Project) -> ProjectOut:
    return ProjectOut.model_validate(p)


@router.post("", status_code=201, response_model=ProjectOut)
def create_project(body: ProjectCreate, db: Session = Depends(get_db),
                   settings: Settings = Depends(get_settings)):
    p = service.create_project(db, settings, body.slug, body.title, body.owner)
    return _project_out(p)


@router.get("", response_model=list[ProjectOut])
def list_projects(status: str | None = Query(default=None),
                  db: Session = Depends(get_db)):
    q = select(Project).order_by(Project.id)
    if status:
        q = q.where(Project.status == ProjectStatus(status))
    return [_project_out(p) for p in db.scalars(q)]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if p is None:
        raise http_404(f"프로젝트 없음: {project_id}")
    return _project_out(p)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if p is None:
        raise http_404(f"프로젝트 없음: {project_id}")
    if body.title is not None:
        p.title = body.title
    if body.status is not None:
        p.status = ProjectStatus(body.status)
    return _project_out(p)


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