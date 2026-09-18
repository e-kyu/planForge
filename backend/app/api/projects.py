# -*- coding: utf-8 -*-
"""프로젝트 관리 API (FR-1)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_db
from ..errors import http_404, http_409
from ..models import Project, ProjectStatus
from ..schemas import ProjectCreate, ProjectOut, ProjectUpdate
from ..workspace import create_workspace, validate_slug

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _project_out(p: Project) -> ProjectOut:
    return ProjectOut.model_validate(p)


@router.post("", status_code=201, response_model=ProjectOut)
def create_project(body: ProjectCreate, db: Session = Depends(get_db),
                   settings: Settings = Depends(get_settings)):
    validate_slug(body.slug)
    exists = db.scalar(select(Project).where(Project.slug == body.slug))
    if exists is not None:
        raise http_409(f"이미 존재하는 slug입니다: {body.slug}")
    ws = create_workspace(settings.workspaces_dir, body.slug)
    p = Project(slug=body.slug, title=body.title, owner=body.owner, workspace_path=str(ws))
    db.add(p)
    db.flush()
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