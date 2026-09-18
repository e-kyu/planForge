# -*- coding: utf-8 -*-
"""팩트 저장소 API (원칙 4) — 인터뷰 확립 팩트 + 수동 팩트."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import http_404
from ..models import Fact, FactOrigin, FactStatus, Project

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