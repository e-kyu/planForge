# -*- coding: utf-8 -*-
"""docloops 모듈 퍼사드 — 타 모듈의 유일한 진입점 (가이드 §3 Facade).

계약: docloops는 리프 모듈 — 이 facade가 타 모듈 facade를 import하지 않는다.
plans(승인 훅)·interview(세션 게이트)·projects(삭제 사슬·생성 시드) 쪽이
이 모듈을 호출하는 방향이다. 커밋은 호출자 트랜잭션에서 (facts.facade 패턴).
"""
from __future__ import annotations

from .application.service import (
    DOC_KINDS,
    delete_project_data,
    doc_label,
    has_doc_layout,
    init_project_loops,
    list_loops,
    on_plan_approved,
    require_session_doc,
)
from .infrastructure.models import DocLoop, DocLoopStatus

__all__ = [
    "DocLoopStatus", "DocLoop", "DOC_KINDS", "doc_label",
    "init_project_loops", "list_loops", "require_session_doc",
    "on_plan_approved", "has_doc_layout", "delete_project_data",
]