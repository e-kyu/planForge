# -*- coding: utf-8 -*-
"""docloops 상태 API (FR-1 확장) — 문서별 선순환 루프 조회.

읽기 표면만 담당한다 — 래치 상태머신은 application/service.py 소관이고, 쓰기 훅
(생성 시드는 projects.create_project, 승인 래치는 plans 승인 경로)에서 온다.

모듈 경계: 타 모듈 접근은 facade 경유(require_project·latest_generations_by_doc) —
docloops는 리프 모듈이므로 이 모듈의 facade·application이 타 facade를 import하지
않는 계약은 유지된다 (presentation api의 facade import는 jobs 선례 표면).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.modules.plans.facade import latest_generations_by_doc
from app.modules.projects.facade import require_project
from app.shared.db import get_db

from ..application.service import list_loops
from .schemas import DocLoopOut

router = APIRouter(tags=["docloops"])


@router.get("/api/projects/{project_id}/docloops", response_model=list[DocLoopOut])
def list_docloops(project_id: int, db: Session = Depends(get_db)):
    """문서 루프 3건(proposal·uiux-design·dev-design 순정렬) — 프로젝트 목록 화면이
    문서 버튼 상태(locked/active/done)를 N+1 없이 알기 위한 읽기 계약.

    doc_loops 행이 없는 프로젝트(레거시)는 []를 반환한다 — 프론트는 빈 목록을
    "레거시 프로젝트"로 보고 문서 버튼을 렌더링하지 않는다.
    """
    require_project(db, project_id)
    latest = latest_generations_by_doc(db, project_id)
    out = []
    for r in list_loops(db, project_id):
        out.append(DocLoopOut.from_row(r, latest.get(r.doc_slug)))
    return out