# -*- coding: utf-8 -*-
"""slug 규칙 — 프로젝트·문서 슬러그 공용.

planforge 엔진은 웹 비의존이므로 `WorkspaceError`를 import하지 않는다 — 검증 예외는
호출자(`app.shared.workspace`)가 만든다.
"""
from __future__ import annotations

import re

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MAX_SLUG_LENGTH = 64


def is_valid_slug(slug: str) -> bool:
    """형식(소문자/숫자/하이픈, 첫 글자 영숫자) + 길이(64자 이하)를 모두 만족하는가."""
    return bool(SLUG_RE.fullmatch(slug or "")) and len(slug) <= MAX_SLUG_LENGTH
