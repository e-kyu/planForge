# -*- coding: utf-8 -*-
"""API 라우터 집계."""
from __future__ import annotations

from fastapi import APIRouter

from . import projects

api_router = APIRouter()
api_router.include_router(projects.router)