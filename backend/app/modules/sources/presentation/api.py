# -*- coding: utf-8 -*-
"""소스 API (FR-2.1, §5 업로드 검증).

- 프로젝트 sources/: 업로드(쓰기 가능)·목록·삭제 — 인터뷰 에이전트가 매 턴 읽는다.
- 글로벌 sources/: 목록만 (서버 운영자가 배치하는 공용 소스 — 읽기 전용).

검증은 shared.workspace.validate_source_file이 전담한다: 확장자 화이트리스트
(.md .txt .json .csv), 용량 상한(2MB), UTF-8 텍스트, 파일명 정규화.
덮어쓰기는 금지(409) — 소스도 기록의 일부다.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.shared.config import Settings, get_settings
from app.shared.db import get_db
from app.shared.errors import http_404, http_409
from app.shared.workspace import SourceError, validate_source_file

from ..facade import project_sources_dir
from .schemas import SourceOut

router = APIRouter(prefix="/api/projects/{project_id}", tags=["sources"])
global_router = APIRouter(prefix="/api/sources", tags=["sources"])


def _list_dir(d: Path, dir_label: str) -> list[SourceOut]:
    out: list[SourceOut] = []
    if d.is_dir():
        for f in sorted(d.iterdir()):
            if f.is_file():
                st = f.stat()
                out.append(SourceOut(name=f.name, size=st.st_size, dir=dir_label,
                                     mtime=st.st_mtime))
    return out


@router.get("/sources", response_model=list[SourceOut])
def list_sources(project_id: int, db: Session = Depends(get_db),
                 settings: Settings = Depends(get_settings)):
    return _list_dir(project_sources_dir(db, project_id), "project")


@router.post("/sources", status_code=201, response_model=SourceOut)
def upload_source(project_id: int, file: UploadFile, db: Session = Depends(get_db),
                  settings: Settings = Depends(get_settings)):
    src = project_sources_dir(db, project_id)
    data = file.file.read()
    try:
        name = validate_source_file(file.filename or "", data)
    except SourceError as e:
        raise http_409(str(e)) from e
    target = src / name
    if target.exists():
        raise http_409(f"같은 이름의 소스가 이미 있습니다: {name}")
    target.write_bytes(data)
    st = target.stat()
    return SourceOut(name=name, size=st.st_size, dir="project", mtime=st.st_mtime)


@router.delete("/sources/{name}", status_code=204)
def delete_source(project_id: int, name: str, db: Session = Depends(get_db),
                  settings: Settings = Depends(get_settings)):
    src = project_sources_dir(db, project_id)
    target = src / name
    if not target.is_file():
        raise http_404(f"소스 없음: {name}")
    target.unlink()


@global_router.get("", response_model=list[SourceOut])
def list_global_sources(settings: Settings = Depends(get_settings)):
    return _list_dir(settings.global_sources_dir, "global")