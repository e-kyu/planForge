# -*- coding: utf-8 -*-
"""디자인 토큰 4종 세트 자동 검증 (원칙 7 — docs/token-checklist.md 흡수).

권위는 theme.py다. tokens.css(프론트 미러)와 theme.py의 대응을 기계 대조하고,
빌더에 토큰 밖 리터럴(직접 색·폰트 하드코딩)이 남지 않았는지 스캔한다.
문서화 편차(--fs-caption·--fs-ui·--margin·상태 색 3종)는 리터럴 동결로 고정 —
theme.py에 권위가 없는 화면 전용 값이므로 theme와 비교하면 오탐이다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import planforge.builders.theme as theme

REPO = Path(__file__).resolve().parent.parent
TOKENS_CSS = REPO / "frontend" / "src" / "shared" / "styles" / "tokens.css"
BUILDERS = [REPO / "backend" / "planforge" / "builders" / "build_ppt.py",
            REPO / "backend" / "planforge" / "builders" / "build_doc.py"]

# 권위 theme.py ↔ CSS 변수 렌더 — 9색 대응표 (색상 추적 단절 방지)
COLOR_MAP = [
    ("NAVY", "--navy"),
    ("BLUE", "--blue"),
    ("LIGHT_BLUE", "--light-blue"),
    ("BG", "--bg"),
    ("BG_SOFT", "--bg-soft"),
    ("TEXT", "--text"),
    ("TEXT_SUB", "--text-sub"),
    ("LINE", "--line"),
    ("ACCENT", "--accent"),
]


def _css_vars() -> dict[str, str]:
    """:root 선언을 --키: 값 으로 수집 (미러 파일 계약 — 간단 파서로 잠금)."""
    text = TOKENS_CSS.read_text(encoding="utf-8")
    return {k: v.strip() for k, v in re.findall(r"(--[\w-]+):\s*([^;]+);", text)}


@pytest.fixture(scope="module")
def css():
    return _css_vars()


# ---------------------------------------------------------------- 색 대응 (9색)

@pytest.mark.parametrize(("token", "var"), COLOR_MAP)
def test_color_tokens_mirror_theme(css, token, var):
    assert var in css, f"tokens.css에 {var} 선언 없음 — 4종 세트 절차 위반"
    assert css[var].lower() == f"#{getattr(theme, token).lower()}"


def test_font_family_mirrors_theme(css):
    assert theme.FONT in css["--font"]


@pytest.mark.parametrize(("token", "var"), [
    ("SIZE_SLIDE_TITLE", "--fs-title"),
    ("SIZE_HEADING", "--fs-heading"),
    ("SIZE_BODY", "--fs-body"),
])
def test_font_size_tokens_mirror_theme(css, token, var):
    assert css[var] == f"{getattr(theme, token)}px"


# ---------------------------------------------------------------- 문서화 편차 (리터럴 동결)

def test_documented_deviations_frozen(css):
    """theme.py에 권위 없는 화면 값 — 편차를 상수 동결로 잠근다.

    --fs-caption: theme.SIZE_CAPTION(10pt)와 달리 화면 표시 배율로 11px,
    --fs-ui: 목업 text-sm 재해석 13px, --margin: MARGIN 0.6in ≈ 24px.
    """
    assert css["--fs-caption"] == "11px"
    assert css["--fs-ui"] == "13px"
    assert css["--margin"] == "24px"


def test_status_colors_frozen(css):
    """상태 색 3종(검수 심각도 FR-4.2) — theme에는 없는 화면·리포트 전용 팔레트."""
    assert css["--danger"] == "#c0392b"
    assert css["--warn"] == "#b7791f"
    assert css["--ok"] == "#2f855a"


def test_screen_only_tokens_present(css):
    """화면 전용 토큰은 대응표 밖이지만 존재는 확인한다 (app 크롬 전용)."""
    for var in ("--surface", "--surface-sub", "--line-soft"):
        assert var in css


# ---------------------------------------------------------------- 빌더 리터럴 스캔

# build_doc.META_LINE_COLOR 레거시 상수 — 표 메타 라인 전용, 이식 유지 (토큰 4종 대상 아님)
ALLOWED_HEX = {"C6D3E2"}


def test_builders_have_no_out_of_theme_literals():
    """빌더는 색·폰트를 theme.py 토큰으로만 쓴다 — 하드코딩 리터럴 0건을 기계 스캔.

    6자리 16진수 문자열 리터럴 중 순수 숫자(EMU 좌표 914400 등)는 제외하고,
    알파벳을 포함한 색 코드만 대상으로 한다. "Malgun Gothic" 직접 기술도 금지.
    """
    for path in BUILDERS:
        text = path.read_text(encoding="utf-8")
        hits = [m for m in re.findall(r"[\"']([0-9A-Fa-f]{6})[\"']", text)
                if m.upper() not in ALLOWED_HEX and any(c.isalpha() for c in m)]
        assert hits == [], f"{path.name}: theme 밖 색 리터럴 {hits} — 4종 세트 절차 위반"
        assert "Malgun Gothic" not in text, f"{path.name}: 폰트 리터럴 — theme.FONT로 대체"