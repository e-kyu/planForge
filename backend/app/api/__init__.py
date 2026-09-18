# -*- coding: utf-8 -*-
"""API 라우터 집계."""
from __future__ import annotations

from fastapi import APIRouter

from . import derivatives, facts, interview, jobs, plans, projects, sources

api_router = APIRouter()
api_router.include_router(projects.router)
api_router.include_router(sources.router)
api_router.include_router(sources.global_router)
api_router.include_router(plans.router)
api_router.include_router(derivatives.router)
api_router.include_router(jobs.router)
api_router.include_router(facts.router)
api_router.include_router(interview.router)