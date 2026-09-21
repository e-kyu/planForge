# -*- coding: utf-8 -*-
"""예외 → HTTP 매핑. 엔진(PlanError 등)과 웹 계층을 분리한다."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from planforge.plan import PlanError

from .workspace import WorkspaceError


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(WorkspaceError)
    async def workspace_error(request: Request, exc: WorkspaceError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(PlanError)
    async def plan_error(request: Request, exc: PlanError):
        # plan 포맷 위반은 클라이언트 입력 검증 실패로 분류 (FR-2.8 게이트)
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # ctx.error 등 JSON 비직렬화 객체를 문자열로 정규화
        errs = []
        for e in exc.errors():
            e = dict(e)
            if "ctx" in e:
                e["ctx"] = {k: str(v) for k, v in (e["ctx"] or {}).items()}
            errs.append(e)
        return JSONResponse(status_code=422, content={"detail": errs})


def http_404(detail: str) -> StarletteHTTPException:
    return StarletteHTTPException(status_code=404, detail=detail)


def http_409(detail: str) -> StarletteHTTPException:
    return StarletteHTTPException(status_code=409, detail=detail)