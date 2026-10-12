# -*- coding: utf-8 -*-
"""소스 API (FR-2.1, §5 업로드 검증).

- 프로젝트 sources/: 업로드(쓰기 가능)·목록·삭제·다운로드 — 인터뷰 에이전트가 매 턴 읽는다.
- 글로벌 sources/: 목록·다운로드 (서버 운영자가 배치하는 공용 소스 — 쓰기·삭제는 읽기 전용).
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

from ..application.zip_sources import extract_zip
from ..facade import project_overview_path, project_sources_dir
from .schemas import OverviewOut, OverviewSave, SkipOut, SourceOut, UploadResult

router = APIRouter(prefix="/api/projects/{project_id}", tags=["sources"])
global_router = APIRouter(prefix="/api/sources", tags=["sources"])

_SOURCE_MEDIA = {".md": "text/markdown", ".txt": "text/plain",
                 ".json": "application/json", ".csv": "text/csv"}


def _list_dir(d: Path, dir_label: str) -> list[SourceOut]:
    """소스 목록 — 하위 디렉토리까지 재귀 수집한다.

    name은 POSIX 상대경로로 고정한다 (read_sources_context의 정렬 키·헤더와 동일
    규약). 플랫 소스는 상대경로 == 파일명이라 기존 출력과 동일하다.
    """
    out: list[SourceOut] = []
    if d.is_dir():
        files = sorted((f for f in d.rglob("*") if f.is_file()),
                       key=lambda f: f.relative_to(d).as_posix())
        for f in files:
            st = f.stat()
            out.append(SourceOut(name=f.relative_to(d).as_posix(),
                                 size=st.st_size, dir=dir_label, mtime=st.st_mtime))
    return out


def _validated_source_path(src: Path, name: str) -> Path:
    """DELETE·download 공용 — sources/ 내 상대 하위경로만 허용한다 (zip 구조 대응).

    빈 경로·`..` 트래버설·절대경로(드라이브 포함)는 404로 통일 거부한다 — 존재 여부
    누설 방지 규약. 역슬래시는 URL에서 구분자로 해석될 수 없어 성분 분해 전 슬래시로
    치환한다 (구분자 문자 자체가 경로 침투). resolve() + containment(is_relative_to)
    는 심링크 등 경로 조작의 최종 방어선이다.
    """
    parts = [p for p in (name or "").replace("\\", "/").split("/") if p]
    if not parts or any(p == ".." for p in parts) or \
       (len(parts) == 1 and len(parts[0]) > 1 and parts[0][1] == ":"
        and parts[0][0].isalpha()):
        raise http_404(f"소스 없음: {name}")
    target = (src / Path(*parts)).resolve()
    if not (target.is_file() and target.is_relative_to(src.resolve())):
        raise http_404(f"소스 없음: {name}")
    return target


def _source_response(target: Path) -> FileResponse:
    """소스 파일 응답 — 확장자별 media-type, 프로젝트/글로벌 download 공용."""
    media = _SOURCE_MEDIA.get(target.suffix.lower())
    if media is None:
        media = "application/octet-stream"
    return FileResponse(target, media_type=media, filename=target.name,
                        content_disposition_type="inline")


@router.get("/sources", response_model=list[SourceOut])
def list_sources(project_id: int, db: Session = Depends(get_db),
                 settings: Settings = Depends(get_settings)):
    return _list_dir(project_sources_dir(db, project_id), "project")


def _source_out(src: Path, rel: str) -> SourceOut:
    """저장 완료 소스의 SourceOut — rel은 플랫 이름 또는 POSIX 상대경로 (목록과 동일 규약)."""
    target = src / rel
    st = target.stat()
    return SourceOut(name=rel, size=st.st_size, dir="project", mtime=st.st_mtime)


@router.post("/sources", status_code=201, response_model=UploadResult)
def upload_source(project_id: int, file: UploadFile, db: Session = Depends(get_db),
                  settings: Settings = Depends(get_settings)):
    """소스 업로드 — .zip은 해제 결과를, 단일 파일은 그대로를 저장한다.

    응답 계약 확장: 기존 단일 SourceOut → UploadResult(saved·skipped) 래핑.
    - zip 멤버의 덮어쓰기 금지는 거부가 아니라 스킵 보고로 원칙을 유지한다 — zip은
      사용자가 일괄 해제 결과를 미리 검증할 수 없는 일괄 경로라 1멤버 충돌로 나머지를
      전부 거부하지 않는다 (경계: "사용자 명시 선택 vs 일괄 해제 결과").
    - 단일 파일의 거부는 409 그대로다 — 명시적으로 고른 파일 하나의 거부를 스킵으로
      조용히 넘기면 사용자가 실패를 인지하지 못한다 (기존 계약 유지).
    - .zip 자체는 소스로 저장되지 않는다 — 해제 결과만 소스가 된다 (_SOURCE_MEDIA에
      .zip 항목 없음 — download 경로를 통과하지 않는다).
    - extract_zip은 2페이즈 설계상 자체 결함(SourceError) 시 어떤 파일도 기록하지
      않았으므로 409 전체 거부로 변환해도 워크스페이스는 무손상이다.
    """
    src = project_sources_dir(db, project_id)
    data = file.file.read()

    if Path(file.filename or "").suffix.lower() == ".zip":
        try:
            rels, skipped = extract_zip(data, src)
        except SourceError as e:
            raise http_409(str(e)) from e
        return UploadResult(saved=[_source_out(src, rel) for rel in rels],
                            skipped=[SkipOut(name=name, reason=reason)
                                     for name, reason in skipped])

    try:
        name = validate_source_file(file.filename or "", data)
    except SourceError as e:
        raise http_409(str(e)) from e
    target = src / name
    if target.exists():
        raise http_409(f"같은 이름의 소스가 이미 있습니다: {name}")
    target.write_bytes(data)
    return UploadResult(saved=[_source_out(src, name)], skipped=[])


@router.delete("/sources/{name:path}", status_code=204)
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


@router.get("/sources/{name:path}/download")
def download_source(project_id: int, name: str, db: Session = Depends(get_db)):
    """소스 대역파일 다운로드 — DELETE /sources/{name}과 대칭 (파일 경로 검증 공유)."""
    target = _validated_source_path(project_sources_dir(db, project_id), name)
    return _source_response(target)


@global_router.get("", response_model=list[SourceOut])
def list_global_sources(settings: Settings = Depends(get_settings)):
    return _list_dir(settings.global_sources_dir, "global")


@global_router.get("/{name:path}/download")
def download_global_source(name: str, settings: Settings = Depends(get_settings)):
    """글로벌 소스 다운로드 — 쓰기·삭제 없는 읽기 전용 경로 (프로젝트 download와 검증 공유)."""
    target = _validated_source_path(settings.global_sources_dir, name)
    return _source_response(target)