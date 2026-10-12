# -*- coding: utf-8 -*-
"""zip 소스 추출 코어 테스트 — extract_zip·sanitize_source_relpath (API 결합 전, step 3에서 결합).

zip fixture는 테스트 코드에서 메모리 생성(io.BytesIO)한다 — tests/fixtures/에
바이너리 fixture 파일을 만들지 않는다.
"""
from __future__ import annotations

import io
import os
import zipfile

import pytest

from app.modules.sources.application.zip_sources import extract_zip
from app.shared.workspace import (
    MAX_SOURCE_BYTES,
    MAX_ZIP_MEMBERS,
    MAX_ZIP_UNCOMPRESSED_BYTES,
    SourceError,
    sanitize_source_relpath,
)


def _zip_bytes(members: list[tuple[str, bytes]]) -> bytes:
    # deflate — 무압축(STORED) 기본값이면 반복 바이너리 멤버가 zip 자체 2MB 상한을
    # 먼저 건드려 멤버별 스킵·총량 케이스를 검증할 수 없다.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in members:
            zf.writestr(name, payload)
    return buf.getvalue()


def _cp949_name_zip(name_kr: str, payload: bytes) -> bytes:
    """EUC-KR 멤버명 zip을 실물처럼 생성 — ASCII placeholder 기록 후 이름 바이트를
    cp949 바이트로 교체한다(길이 동일 → 오프셋 무변경, UTF-8 플래그 없음)."""
    raw = name_kr.encode("cp949")
    placeholder = "m" * len(raw)
    blob = bytearray(_zip_bytes([(placeholder, payload)]))
    marker = placeholder.encode("ascii")
    i = blob.find(marker)            # 로컬 파일 헤더의 이름
    blob[i:i + len(raw)] = raw
    j = blob.rfind(marker)           # 중앙 디렉터리의 이름
    blob[j:j + len(raw)] = raw
    return bytes(blob)


def _files(dest) -> list[str]:
    return sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())


def _data_dir(root, name: str):
    d = root / name
    d.mkdir(parents=True)
    return d


# ---------------------------------------------------------------- sanitize_source_relpath

def test_sanitize_relpath_posix_and_substitution():
    assert sanitize_source_relpath("sub\\dir\\파일.md") == "sub/dir/파일.md"
    assert sanitize_source_relpath("a<b>/c|d?.md") == "a_b_/c_d_.md"
    assert sanitize_source_relpath('dir "x"/e*.csv') == "dir _x_/e_.csv"
    assert sanitize_source_relpath("끝공백.txt ") == "끝공백.txt"
    assert sanitize_source_relpath("점뒤. . ./report.json") == "점뒤/report.json"


def test_sanitize_relpath_rejects_structural_traps():
    for bad in ("../evil.md", "a/../b.md", "a/./b.md", "/abs.md", "\\abs.md",
                "C:/x.md", "c:\\x.md", ".__x.md", "._a.md", ".DS_Store",
                ".hidden/x.md", "__MACOSX/회의.md", "__MACOSX_doc/x.md",
                "dir/", ".", "", "   "):
        assert sanitize_source_relpath(bad) is None, bad
    # 전부 금지 문자인 성분은 치환 규약이 유효성 검증의 소관이 아니라 구조 기각이 대상이다.
    assert sanitize_source_relpath("a/???.md") == "a/___.md"


# ---------------------------------------------------------------- extract_zip

def test_structure_preserved(tmp_path):
    data = _zip_bytes([("sub/회의.md", "하위 본문".encode()),
                       ("메모.txt", "최상위".encode())])
    saved, skipped = extract_zip(data, tmp_path)
    assert saved == ["sub/회의.md", "메모.txt"]
    assert skipped == []
    assert (tmp_path / "sub" / "회의.md").read_text(encoding="utf-8") == "하위 본문"


def test_unsupported_extension_skipped(tmp_path):
    data = _zip_bytes([("img/logo.png", b"\x89PNG\r\n\x1a\n"),
                       ("a.md", "본문".encode())])
    saved, skipped = extract_zip(data, tmp_path)
    assert saved == ["a.md"]
    assert skipped == [("img/logo.png", "지원하지 않는 확장자")]
    assert _files(tmp_path) == ["a.md"]


def test_non_utf8_text_skipped(tmp_path):
    data = _zip_bytes([("legacy.txt", "프로젝트 기획".encode("cp949")),
                       ("ok.md", "정상".encode())])
    saved, skipped = extract_zip(data, tmp_path)
    assert saved == ["ok.md"]
    assert skipped == [("legacy.txt", "UTF-8 텍스트 파일만 저장할 수 있습니다")]
    assert not (tmp_path / "legacy.txt").exists()


def test_traversal_and_absolute_members_rejected(tmp_path):
    data = _zip_bytes([("../evil.md", "악성".encode()),
                       ("a/../../escape.md", "탈출".encode()),
                       ("C:/abs.md", "드라이브".encode()),
                       ("/root/abs.md", "루트".encode()),
                       ("ok.md", "정상".encode())])
    saved, skipped = extract_zip(data, tmp_path)
    assert saved == ["ok.md"]
    assert all(reason == "지원하지 않는 경로" for _, reason in skipped)
    assert _files(tmp_path) == ["ok.md"]                      # dest 내 성분만
    assert not (tmp_path.parent / "evil.md").exists()          # dest 밖 기록 없음


def test_macosx_and_hidden_members_rejected(tmp_path):
    data = _zip_bytes([("__MACOSX/doc/._notes.md", "메타".encode()),
                       (".DS_Store", "숨김".encode()),
                       (".hidden/plan.md", "숨김2".encode()),
                       ("ok.md", "정상".encode())])
    saved, skipped = extract_zip(data, tmp_path)
    assert saved == ["ok.md"]
    assert sorted(skipped) == [(".DS_Store", "지원하지 않는 경로"),
                               (".hidden/plan.md", "지원하지 않는 경로"),
                               ("__MACOSX/doc/._notes.md", "지원하지 않는 경로")]
    assert _files(tmp_path) == ["ok.md"]


def test_cp949_member_name_restored(tmp_path):
    data = _cp949_name_zip("한글문서.md", "본문 내용".encode())
    saved, skipped = extract_zip(data, tmp_path)
    assert skipped == []
    assert saved == ["한글문서.md"]                     # 복원된 멤버명으로 저장
    assert (tmp_path / "한글문서.md").read_text(encoding="utf-8") == "본문 내용"


def test_oversized_member_skipped_not_rejected(tmp_path):
    data = _zip_bytes([("big.txt", b"x" * (MAX_SOURCE_BYTES + 1)),
                       ("ok.md", "정상".encode())])
    saved, skipped = extract_zip(data, tmp_path)
    assert saved == ["ok.md"]                          # zip 자체는 2MB 이하 → 전체 거부 아님
    assert skipped == [("big.txt", "파일이 너무 큽니다")]
    assert _files(tmp_path) == ["ok.md"]


def test_existing_file_conflict_skipped(tmp_path):
    (tmp_path / "회의.md").write_text("기존 내용", encoding="utf-8")
    data = _zip_bytes([("회의.md", "zip 내용".encode())])
    saved, skipped = extract_zip(data, tmp_path)
    assert saved == []
    assert skipped == [("회의.md", "같은 이름의 소스가 이미 있습니다")]
    assert (tmp_path / "회의.md").read_text(encoding="utf-8") == "기존 내용"  # 무손실


@pytest.mark.filterwarnings("ignore::UserWarning")  # 중복 멤버 기록은 이 테스트의 의도적 재현
def test_internal_duplicate_skipped(tmp_path):
    data = _zip_bytes([("dup.md", "첫번째".encode()), ("dup.md", "두번째".encode())])
    saved, skipped = extract_zip(data, tmp_path)
    assert saved == ["dup.md"]
    assert skipped == [("dup.md", "같은 이름의 소스가 이미 있습니다")]
    assert (tmp_path / "dup.md").read_text(encoding="utf-8") == "첫번째"


def test_all_members_skipped_writes_nothing(tmp_path):
    data = _zip_bytes([("img/photo.png", b"\x89PNG"),
                       ("legacy.txt", "레거시".encode("cp949")),
                       ("../escape.md", "탈출".encode())])
    saved, skipped = extract_zip(data, tmp_path)
    assert saved == []
    assert len(skipped) == 3
    assert _files(tmp_path) == []                       # 파일은 반드시 0개


def test_corrupt_zip_raises(tmp_path):
    with pytest.raises(SourceError):
        extract_zip(b"\x00this is not a zip file at all\x00\x01\x02" + os.urandom(64),
                    tmp_path)
    assert _files(tmp_path) == []


def test_member_count_exceeded_raises(tmp_path):
    members = [(f"f{i:03}.txt", f"내용 {i}".encode()) for i in range(MAX_ZIP_MEMBERS + 1)]
    with pytest.raises(SourceError):
        extract_zip(_zip_bytes(members), tmp_path)
    assert _files(tmp_path) == []


def test_uncompressed_total_exceeded_raises(tmp_path):
    payload = b"a" * 1_700_000                          # 1.7MB × 5 ≈ 8.5MB > 8MB (개별은 2MB 이하)
    members = [(f"big{i}.txt", payload) for i in range(5)]
    with pytest.raises(SourceError):
        extract_zip(_zip_bytes(members), tmp_path)
    assert _files(tmp_path) == []


def test_zip_itself_over_max_bytes_rejected(tmp_path):
    blob = os.urandom(MAX_SOURCE_BYTES + 64 * 1024)     # 비압축성 → zip 크기 > 2MB
    with pytest.raises(SourceError):
        extract_zip(_zip_bytes([("noise.txt", blob)]), tmp_path)
    assert _files(tmp_path) == []


def test_max_members_boundary_accepted(tmp_path):
    members = [(f"f{i:03}.txt", f"내용 {i}".encode()) for i in range(MAX_ZIP_MEMBERS)]
    saved, skipped = extract_zip(_zip_bytes(members), tmp_path)
    assert saved == [m[0] for m in members]
    assert skipped == []


def test_total_boundary_accepted(tmp_path):
    payload = b"a" * 1_500_000                          # 1.5MB × 5 = 7.5MB ≤ 8MB
    members = [(f"big{i}.txt", payload) for i in range(5)]
    saved, _ = extract_zip(_zip_bytes(members), tmp_path)
    assert saved == [m[0] for m in members]