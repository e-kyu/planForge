# -*- coding: utf-8 -*-
"""zip 소스 추출 (소스 zip 지원) — presentation 미의존 순수 로직.

ZipFile.extract()/extractall()은 멤버 이름이 그대로 파일시스템 경로가 되어
Zip Slip이 성립한다 — 이 모듈은 멤버를 zf.open(info).read()로 **바이트만**
꺼내 sanitize_source_relpath로 정규화한 상대경로에 직접 기록한다.
"""
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

from app.shared.workspace import (
    MAX_SOURCE_BYTES,
    MAX_ZIP_BYTES,
    MAX_ZIP_MEMBERS,
    MAX_ZIP_UNCOMPRESSED_BYTES,
    SOURCE_EXTS,
    SourceError,
    sanitize_source_relpath,
)


def _restore_member_name(info: zipfile.ZipInfo) -> str:
    """멤버명 인코딩 복원 — UTF-8 플래그(0x800)가 없으면 cp437→cp949 복원을 시도한다.

    한글 Windows 탐색기로 압축한 zip(EUC-KR 멤버명)은 UTF-8 플래그가 없어 Python이
    cp437로 디코딩한다. cp949 복원에 실패하면(영문명 등) 원값을 유지한다.
    """
    name = info.orig_filename  # original_filename 별칭은 3.13+ — 3.12 호환 명칭
    if info.flag_bits & 0x800:
        return name
    try:
        return name.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def _admit_member(info: zipfile.ZipInfo, shown: str, dest: Path,
                  seen: set[str]) -> tuple[str | None, str | None]:
    """채택 판정 — 크기/경로/중복 검사. (상대경로, None) 또는 (None, 기각 사유)."""
    rel = sanitize_source_relpath(shown)
    if rel is None:
        return None, "지원하지 않는 경로"
    if os.path.splitext(rel)[1].lower() not in SOURCE_EXTS:
        return None, "지원하지 않는 확장자"
    if info.file_size > MAX_SOURCE_BYTES:
        return None, "파일이 너무 큽니다"
    if rel in seen or (dest / rel).exists():
        return None, "같은 이름의 소스가 이미 있습니다"
    return rel, None


def _scan_member(info: zipfile.ZipInfo, dest: Path, seen: set[str]
                 ) -> tuple[tuple[zipfile.ZipInfo, str, str] | None,
                            tuple[str, str] | None]:
    """1페이즈 멤버 판정 — (채택 (info, 표기명, 상대경로), None) 또는 (None, 스킵)."""
    shown = _restore_member_name(info)
    if info.is_dir():
        return None, (shown, "디렉터리 항목")
    rel, reason = _admit_member(info, shown, dest, seen)
    if rel is None:
        return None, (shown, reason)
    return (info, shown, rel), None


def _write_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, shown: str, rel: str,
                  dest: Path) -> tuple[str | None, tuple[str, str] | None]:
    """2페이즈 쓰기 — 실측 재검사 후 기록. (저장 경로, None) 또는 (None, 스킵)."""
    payload = zf.open(info).read(MAX_SOURCE_BYTES + 1)
    if len(payload) > MAX_SOURCE_BYTES:
        return None, (shown, "파일이 너무 큽니다")
    try:
        payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, (shown, "UTF-8 텍스트 파일만 저장할 수 있습니다")
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)  # 검증 통과한 원본 바이트 그대로 — BOM 포함 원형 유지
    return rel, None


def extract_zip(data: bytes, dest: Path) -> tuple[list[str], list[tuple[str, str]]]:
    """zip 바이트 → dest(워크스페이스 sources/) 기록. (저장된 상대경로, 스킵 [(멤버 원명, 사유)]).

    자체 결함(zip 크기 초과·손상·멤버 수 초과·해제 총량 초과)은 SourceError로
    전체 거부 — 이 시점 어떤 파일도 기록되지 않는다. 개별 멤버 결함은 스킵으로
    보고하고 나머지를 저장한다. 기존 소스는 절대 덮지 않는다(덮어쓰기 금지 원칙).
    """
    if len(data) > MAX_ZIP_BYTES:
        raise SourceError(f"zip 파일이 너무 큽니다 (최대 {MAX_ZIP_BYTES // (1024 * 1024)}MB)")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise SourceError("손상된 zip 파일입니다") from e

    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_MEMBERS:
            raise SourceError(f"zip 멤버 수가 너무 많습니다 (최대 {MAX_ZIP_MEMBERS}개)")
        if sum(i.file_size for i in infos) > MAX_ZIP_UNCOMPRESSED_BYTES:
            raise SourceError("zip 압축 해제 총량이 너무 큽니다 "
                              f"(최대 {MAX_ZIP_UNCOMPRESSED_BYTES // (1024 * 1024)}MB)")

        # 1페이즈 — 사전 스캔: 읽을 멤버를 확정한다. 스킵 확정 멤버는 절대 읽지 않는다
        # (비화이트리스트 바이너리를 읽는 비용을 원천 배제 — 압축비 조작 공격 방어).
        collected: list[tuple[zipfile.ZipInfo, str, str]] = []  # (info, 표기명, 상대경로)
        skipped: list[tuple[str, str]] = []
        seen: set[str] = set()
        for info in infos:
            admitted, skip = _scan_member(info, dest, seen)
            if admitted is None:
                skipped.append(skip)
                continue
            seen.add(admitted[2])
            collected.append(admitted)

        # 2페이즈 — 수집 확정 멤버만 순서대로 읽고 기록. 실측 재검사로 메타데이터
        # 위조(선언 file_size < 실제)를 이중 방어한다.
        saved: list[str] = []
        for info, shown, rel in collected:
            saved_rel, skip = _write_member(zf, info, shown, rel, dest)
            if saved_rel is None:
                skipped.append(skip)
                continue
            saved.append(saved_rel)
        return saved, skipped