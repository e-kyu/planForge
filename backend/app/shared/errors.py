# -*- coding: utf-8 -*-
"""예외 → HTTP 매핑. 엔진(PlanError 등)과 웹 계층을 분리한다.

오류 응답 단일 스키마 (가이드 §5.1): 상태 코드 + 오류 코드 + 메시지.
- code: not_found | conflict | validation_error | request_validation
- detail: 기존 메시지 그대로 — 프론트는 detail만 써도 동작한다 (계약 하위호환).
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from planforge.plan import PlanError

from .workspace import WorkspaceError


class CodedHTTPError(StarletteHTTPException):
    """오류 코드를 함께 실는 HTTP 예외 (§5.1 단일 스키마)."""

    def __init__(self, status_code: int, detail: str, code: str):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code


def http_404(detail: str) -> CodedHTTPError:
    return CodedHTTPError(404, detail, "not_found")


def http_409(detail: str) -> CodedHTTPError:
    return CodedHTTPError(409, detail, "conflict")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(CodedHTTPError)
    async def coded_error(request: Request, exc: CodedHTTPError):
        return JSONResponse(status_code=exc.status_code,
                            content={"detail": exc.detail, "code": exc.code})

    @app.exception_handler(StarletteHTTPException)
    async def plain_http_error(request: Request, exc: StarletteHTTPException):
        # CodedHTTPError가 아닌 일반 HTTPException — detail만 (기본 계약 유지)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail},
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(WorkspaceError)
    async def workspace_error(request: Request, exc: WorkspaceError):
        return JSONResponse(status_code=422,
                            content={"detail": str(exc), "code": "validation_error"})

    @app.exception_handler(PlanError)
    async def plan_error(request: Request, exc: PlanError):
        # plan 포맷 위반은 클라이언트 입력 검증 실패로 분류 (FR-2.8 게이트)
        return JSONResponse(status_code=422,
                            content={"detail": str(exc), "code": "validation_error"})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # ctx.error 등 JSON 비직렬화 객체를 문자열로 정규화
        errs = []
        for e in exc.errors():
            e = dict(e)
            if "ctx" in e:
                e["ctx"] = {k: str(v) for k, v in (e["ctx"] or {}).items()}
            errs.append(e)
        return JSONResponse(status_code=422,
                            content={"detail": errs, "code": "request_validation"})