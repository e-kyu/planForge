# -*- coding: utf-8 -*-
"""소스 API (FR-2.1, §5 업로드 검증).

- 프로젝트 sources/: 업로드(쓰기 가능)·목록·삭제·다운로드 — 인터뷰 에이전트가 매 턴 읽는다.
- 글로벌 sources/: 목록만 (서버 운영자가 배치하는 공용 소스 — 읽기 전용).
- 개요 문서 (sources/overview.md): 소스 탭에서 웹으로 작성·편집하는 특수 소스 —
  인터뷰 기본자료 전용(결과물 생성 체인 미사용). 파일이 곧 SSOT인 fs 네이티브 문서로,
  편집 경로(PUT /overview)만 다른 소스의 덮어쓰기 금지(409) 규칙의 예외다.

검증은 shared.workspace.validate_source_file이 전담한다: 확장자 화이트리스트
(.md .txt .json .csv), 용량 상한(2MB), UTF-8 텍스트, 파일명 정규화.
덮어쓰기는 금지(409) — 소스도 기록의 일부다.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.shared.config import Settings, get_settings
from app.shared.db import get_db
from app.shared.errors import http_404, http_409
from app.shared.workspace import (
    SourceError,
    validate_overview_content,
    validate_source_file,
)

from ..facade import project_overview_path, project_sources_dir
from .schemas import OverviewOut, OverviewSave, SourceOut

router = APIRouter(prefix="/api/projects/{project_id}", tags=["sources"])
global_router = APIRouter(prefix="/api/sources", tags=["sources"])

_SOURCE_MEDIA = {".md": "text/markdown", ".txt": "text/plain",
                 ".json": "application/json", ".csv": "text/csv"}


def _list_dir(d: Path, dir_label: str) -> list[SourceOut]:
    out: list[SourceOut] = []
    if d.is_dir():
        for f in sorted(d.iterdir()):
            if f.is_file():
                st = f.stat()
                out.append(SourceOut(name=f.name, size=st.st_size, dir=dir_label,
                                     mtime=st.st_mtime))
    return out


def _validated_source_path(src: Path, name: str) -> Path:
    """DELETE·download 공용 — sources/ 밖(트래버설) 접근을 차단하고 파일을 확정한다."""
    if any(sep in name for sep in ("/", "\\")) or ".." in name:
        raise http_404(f"소스 없음: {name}")
    target = src / name
    if not target.is_file():
        raise http_404(f"소스 없음: {name}")
    return target


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
    target = _validated_source_path(src, name)
    target.unlink()


@router.get("/overview", response_model=OverviewOut)
def get_overview(project_id: int, db: Session = Depends(get_db)):
    """개요 문서 조회 — 파일 부재는 오류가 아니라 exists=False (에디터의 빈 뼈대 시작용)."""
    target = project_overview_path(db, project_id)
    if not target.is_file():
        return OverviewOut(exists=False, content="", size=0, mtime=None)
    try:
        text = target.read_text(encoding="utf-8-sig")  # BOM 제거 + universal newlines → LF
    except UnicodeDecodeError as e:
        raise http_409("개요 문서가 UTF-8 텍스트가 아닙니다 — 파일을 직접 확인해 주세요") from e
    return OverviewOut(exists=True, content=text, size=target.stat().st_size,
                       mtime=target.stat().st_mtime)


@router.put("/overview", response_model=OverviewOut)
def save_overview(project_id: int, body: OverviewSave, db: Session = Depends(get_db)):
    """개요 문서 업서트 — 덮어쓰기가 허용되는 유일한 소스 경로 (개요 문서 docstring 참조)."""
    target = project_overview_path(db, project_id)
    try:
        content = validate_overview_content(body.content)
    except SourceError as e:
        raise http_409(str(e)) from e
    target.write_bytes(content.encode("utf-8"))  # 개행 무변환 — LF 고정 (Windows 개행 변환 회피)
    return OverviewOut(exists=True, content=content, size=target.stat().st_size,
                       mtime=target.stat().st_mtime)


@router.get("/sources/{name}/download")
def download_source(project_id: int, name: str, db: Session = Depends(get_db)):
    """소스 대역파일 다운로드 — DELETE /sources/{name}과 대칭 (파일 경로 검증 공유)."""
    src = project_sources_dir(db, project_id)
    target = _validated_source_path(src, name)
    media = _SOURCE_MEDIA.get(target.suffix.lower())
    if media is None:
        media = "application/octet-stream"
    return FileResponse(target, media_type=media, filename=name,
                        content_disposition_type="inline")


@global_router.get("", response_model=list[SourceOut])
def list_global_sources(settings: Settings = Depends(get_settings)):
    return _list_dir(settings.global_sources_dir, "global")