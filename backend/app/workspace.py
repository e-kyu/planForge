# -*- coding: utf-8 -*-
"""워크스페이스 관리 (legacy 디렉토리 규약 유지 — §3.1).

workspaces/<slug>/{work,output,docs,sources,assets}
- work/   : 파생물 중간 파일 (slides.json/report.json — derive 경로만 기록, 원칙 1)
- output/ : 빌더 산출물 (채번 append-only, 원칙 5)
- docs/   : interview-log.md 미러 등
- sources/: 프로젝트 소스 (FR-2.1 인터뷰 소스 확인)
- assets/ : 템플릿 등
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

WORKSPACE_SUBDIRS = ("work", "output", "docs", "sources", "assets")


class WorkspaceError(ValueError):
    pass


def validate_slug(slug: str) -> str:
    if not SLUG_RE.fullmatch(slug or ""):
        raise WorkspaceError(
            f"slug는 ASCII 소문자/숫자/하이픈(첫 글자는 영숫자)만 허용합니다: {slug!r}"
        )
    if len(slug) > 64:
        raise WorkspaceError("slug는 64자 이하여야 합니다")
    return slug


def create_workspace(root: Path, slug: str) -> Path:
    """프로젝트 워크스페이스 자동 생성 (FR-1.2). 기존 디렉토리면 오류."""
    validate_slug(slug)
    ws = root / slug
    if ws.exists():
        raise WorkspaceError(f"워크스페이스가 이미 존재합니다: {ws}")
    for sub in WORKSPACE_SUBDIRS:
        (ws / sub).mkdir(parents=True, exist_ok=False)
    return ws


def workspace_path(settings, slug: str) -> Path:
    validate_slug(slug)
    return settings.workspaces_dir / slug


def ensure_workspace_dirs(ws: Path) -> None:
    for sub in WORKSPACE_SUBDIRS:
        (ws / sub).mkdir(parents=True, exist_ok=True)


def write_plan_mirror(ws: Path, markdown: str) -> Path:
    """DB plans.markdown을 plan.md 미러로 기록 (바이트 동일 — 원칙 1).

    미러는 파생물이 아니라 엔진(Deriver/파서)이 읽는 파일 형태일 뿐이며,
    콘텐츠 원본은 DB plans 행이다.
    """
    p = ws / "plan.md"
    p.write_text(markdown, encoding="utf-8")
    return p


def write_interview_log_mirror(ws: Path, fact_lines: list[str]) -> Path:
    """확정 팩트를 docs/interview-log.md에 누적 기록 (원칙 4 — legacy 팩트 저장소 형식 유지)."""
    docs = ws / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    log = docs / "interview-log.md"
    if not log.exists():
        log.write_text("# interview-log\n\n", encoding="utf-8")
    with log.open("a", encoding="utf-8") as f:
        for line in fact_lines:
            f.write(line + "\n")
    return log


def compact_interview_log(ws: Path, active_lines: list[str],
                          archived_lines: list[str]) -> tuple[Path, Path]:
    """팩트 압축 반영 (FR-6.1) — 활성 로그를 통합본으로 재작성 + archive로 이전 항목 이동.

    legacy compact-log.md 절차 2~3 이식: 활성 로그는 남은 활성 팩트만 남기고,
    archive 파일이 없으면 동일 헤더 구조로 생성해 상단에 '참고용' 안내를 명시한다.
    DB Fact 행이 권위이며 이 함수는 미러만 다시 쓴다 (SSOT — 원칙 1).
    """
    docs = ws / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    log = docs / "interview-log.md"
    body = "# interview-log\n\n"
    if active_lines:
        body += "\n".join(active_lines) + "\n"
    log.write_text(body, encoding="utf-8")
    arch = docs / "interview-log-archive.md"
    if not arch.exists():
        arch.write_text(
            "# interview-log-archive\n\n"
            "압축 시 밀어낸 이전 팩트 이력. 참고용으로만 읽는다.\n\n",
            encoding="utf-8")
    with arch.open("a", encoding="utf-8") as f:
        for line in archived_lines:
            f.write(line + "\n")
    return log, arch


# ---------------------------------------------------------------- 소스 파일 (FR-2.1, §5 업로드 검증)

SOURCE_EXTS = (".md", ".txt", ".json", ".csv")  # read_sources_context와 동일 화이트리스트
MAX_SOURCE_BYTES = 2 * 1024 * 1024  # 2MB — 인터뷰 컨텍스트 주입용 텍스트 소스의 상한
FORBIDDEN_FILENAME_CHARS = '<>:"/\\|?*'  # Windows 금지 문자 (legacy _sanitize_title 규약 계열)


class SourceError(ValueError):
    pass


def sanitize_source_filename(name: str) -> str:
    """업로드 파일명 정규화: 경로 성분 제거 + Windows 금지 문자 치환.

    - 경로 분리(/ \\)와 .. 트래버설은 성분 제거로 무력화하고,
    - 금지 문자는 '_'로 치환 후 트레일링 공백/점을 제거한다 (Windows 규약).
    """
    base = os.path.basename((name or "").replace("\\", "/")).strip()
    if not base or base in (".", ".."):
        raise SourceError("파일명이 비어 있거나 올바르지 않습니다")
    cleaned = "".join("_" if c in FORBIDDEN_FILENAME_CHARS else c for c in base).strip(" .")
    if not cleaned or cleaned.startswith("."):
        raise SourceError(f"허용되지 않는 파일명입니다: {name!r}")
    return cleaned


def validate_source_file(name: str, data: bytes) -> str:
    """업로드 검증(§5): 확장자 화이트리스트·용량 상한·UTF-8 텍스트. 정규화된 이름 반환."""
    cleaned = sanitize_source_filename(name)
    ext = os.path.splitext(cleaned)[1].lower()
    if ext not in SOURCE_EXTS:
        raise SourceError(
            f"지원하지 않는 확장자입니다 ({'/'.join(SOURCE_EXTS)}만 허용): {cleaned}")
    if len(data) > MAX_SOURCE_BYTES:
        raise SourceError(f"파일이 너무 큽니다 (최대 {MAX_SOURCE_BYTES // (1024 * 1024)}MB)")
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise SourceError("UTF-8 텍스트 파일만 업로드할 수 있습니다") from e
    return cleaned


def read_sources_context(sources_dirs: list[Path], max_chars: int = 8000) -> str:
    """인터뷰 소스 컨텍스트 수집 (FR-2.1). 텍스트 파일만, 파일별 크기 상한."""
    parts: list[str] = []
    for d in sources_dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if not f.is_file():
                continue
            if f.suffix.lower() not in (".md", ".txt", ".json", ".csv"):
                continue
            try:
                text = f.read_text(encoding="utf-8-sig")[:max_chars]
            except (UnicodeDecodeError, OSError):
                continue
            parts.append(f"### 소스: {f.name}\n{text}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------- 원자적 빌드 (§5 원자성 + 원칙 5)

BUILD_VER_RE = re.compile(r"_v(\d+)\.[A-Za-z]+$")


def atomic_build(ws: Path, run_builder) -> list[Path]:
    """빌더를 temp output dir에서 실행해 output/으로 원자 이동한다.

    - 채번 연속성: 기존 output 파일을 tmp에 복사해 두므로 빌더의 _next_version glob이
      기존 vNN을 보고 vNN+1을 만든다 (빌더 코드 무변경).
    - 원자성: 산출물은 완성된 파일만 os.replace로 output에 나타난다 (crash 시 부분 파일 없음).
    - run_builder(tmp_dir)는 동기 빌더 실행 함수. 새로 생성된 파일명 리스트를 반환한다.
    """
    out = ws / "output"
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / ".tmp-build"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    existing: dict[str, bytes] = {}
    try:
        for f in sorted(out.iterdir()):
            if f.is_file():
                existing[f.name] = f.read_bytes()
                shutil.copy2(f, tmp / f.name)

        run_builder(tmp)

        made: list[Path] = []
        for f in sorted(tmp.iterdir()):
            if not f.is_file() or f.name in existing:
                continue
            target = out / f.name
            os.replace(f, target)  # 동일 볼륨 — 원자 이동
            made.append(target)
        return made
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


def parse_build_filename(name: str) -> tuple[str, int, str] | None:
    """`<title>_vNN.<ext>` → (title, version_no, ext). 버전 파일이 아니면 None."""
    m = BUILD_VER_RE.search(name)
    if not m:
        return None
    title = name[: m.start()]
    ext = name.rsplit(".", 1)[1].lower()
    return title, int(m.group(1)), ext