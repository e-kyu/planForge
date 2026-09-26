# -*- coding: utf-8 -*-
"""프로젝트 유스케이스 — 생성·삭제 오케스트레이션.

delete_project는 각 모듈 퍼사드의 delete_*를 자식 → 부모 순서로 호출한다
(SQLite FK ON 전제) — 타 모듈 테이블을 직접 건드리지 않는다 (가이드 §3).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules import derivatives, facts, interview, jobs, plans, review
from app.shared.errors import http_404, http_409
from app.shared.workspace import create_workspace, validate_slug

from ..infrastructure.models import Project


def create_project(db: Session, settings, slug: str, title: str,
                   owner: str | None) -> Project:
    """프로젝트 생성 (FR-1.1) — slug 검증·중복 검사·워크스페이스 자동 생성."""
    validate_slug(slug)
    exists = db.scalar(select(Project).where(Project.slug == slug))
    if exists is not None:
        raise http_409(f"이미 존재하는 slug입니다: {slug}")
    ws = create_workspace(settings.workspaces_dir, slug)
    p = Project(slug=slug, title=title, owner=owner, workspace_path=str(ws))
    db.add(p)
    db.flush()
    return p


def delete_project(db: Session, project_id: int) -> Project:
    """프로젝트 하드 삭제 — 추적성 사슬(§5) 전체를 함께 제거한다.

    대기/실행 중 job이 있으면 409로 막는다(단일 워커 직렬 전제 — 실행 도중
    프로젝트가 사라지는 것 방지). 파일 삭제는 커밋 후 프레젠테이션 계층이
    수행한다(파일보다 레코드가 권위).
    """
    p = db.get(Project, project_id)
    if p is None:
        raise http_404(f"프로젝트 없음: {project_id}")
    if jobs.facade.has_busy_jobs(db, project_id):
        raise http_409("대기 중이거나 실행 중인 작업이 있어 삭제할 수 없습니다")

    review.facade.delete_project_data(db, project_id)
    derivatives.facade.delete_project_data(db, project_id)
    facts.facade.delete_project_facts(db, project_id)
    interview.facade.delete_project_data(db, project_id)
    plans.facade.delete_project_plans(db, project_id)
    jobs.facade.delete_project_jobs(db, project_id)
    db.delete(p)
    return p