# -*- coding: utf-8 -*-
"""API 라우터 집계 — 모듈 presentation 라우터를 기존 계약 순서 그대로 포함한다.

라우트 집계만 담당한다 — 도메인 로직은 각 모듈의 presentation/application에.
"""
from __future__ import annotations

from fastapi import APIRouter

from .modules.derivatives.presentation.api import router as derivatives_router
from .modules.facts.presentation.api import router as facts_router
from .modules.interview.presentation.api import router as interview_router
from .modules.jobs.presentation.api import router as jobs_router
from .modules.plans.presentation.api import router as plans_router
from .modules.projects.presentation.api import router as projects_router
from .modules.review.presentation.api import router as reviews_router
from .modules.sources.presentation.api import (
    global_router as sources_global_router,
    router as sources_router,
)

api_router = APIRouter()
api_router.include_router(projects_router)
api_router.include_router(sources_router)
api_router.include_router(sources_global_router)
api_router.include_router(plans_router)
api_router.include_router(derivatives_router)
api_router.include_router(jobs_router)
api_router.include_router(facts_router)
api_router.include_router(interview_router)
api_router.include_router(reviews_router)