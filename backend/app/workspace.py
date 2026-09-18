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

import re
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