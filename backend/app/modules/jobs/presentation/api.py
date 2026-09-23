# -*- coding: utf-8 -*-
"""작업 큐 조회 API — job 상태 폴링 (§3.1: job 상태 조회 화면도 같은 테이블)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.shared.db import get_db
from app.shared.errors import http_404

from ..infrastructure.models import Job
from .schemas import JobOut

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise http_404(f"작업 없음: {job_id}")
    return JobOut.model_validate(job)


@router.get("/projects/{project_id}/jobs", response_model=list[JobOut])
def list_jobs(project_id: int, db: Session = Depends(get_db)):
    jobs = db.scalars(
        select(Job).where(Job.project_id == project_id).order_by(Job.id)
    )
    return [JobOut.model_validate(j) for j in jobs]