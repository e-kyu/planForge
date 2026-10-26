# -*- coding: utf-8 -*-
"""산출물 파일명 규약 — `<문서 제목>_vNN.<ext>` (원칙 5 무손실 채번).

파싱은 기존 `app.shared.workspace.parse_build_filename`과 동일 동작이다 — 버전 파일이
아니면 None, 확장자는 소문자로 정규화한다. 포맷은 `v{NN:02d}` zero-pad.
"""
from __future__ import annotations

import re

BUILD_VER_RE = re.compile(r"_v(\d+)\.[A-Za-z]+$")


def parse_build_filename(name: str) -> tuple[str, int, str] | None:
    """`<title>_vNN.<ext>` → (title, version_no, ext). 버전 파일이 아니면 None."""
    m = BUILD_VER_RE.search(name)
    if not m:
        return None
    title = name[: m.start()]
    ext = name.rsplit(".", 1)[1].lower()
    return title, int(m.group(1)), ext


def format_build_filename(title: str, version_no: int, ext: str) -> str:
    """`f"{title}_v{version_no:02d}.{ext}"` — 기존 빌더 채번 표기와 동일."""
    return f"{title}_v{version_no:02d}.{ext}"
