# -*- coding: utf-8 -*-
"""plan.md 결정론 파서의 데이터 모델.

plan.md 포맷의 권위는 본 파서와 계약 fixture(tests/fixtures/plan.sample.md)가 함께 잠근다.
파서는 콘텐츠를 한 글자도 바꾸지 않는다 (수치·표·차트·(미확정)·근거/출처 문자열 원본 유지).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# plan.md 유형 표기 (한글) → slides.json 유형 (영문 7종). SKILL.md와 동일 세트.
SLIDE_TYPES_KO_TO_EN = {
    "표지": "cover",
    "목차": "toc",
    "2단": "two-col",
    "표": "table",
    "차트": "chart",
    "구성": "arch",
    "마무리": "closing",
}
# 본문형 유형 (슬라이드 번호 표기 대상 — SKILL.md 공통 규칙)
CONTENT_TYPES = ("two-col", "table", "chart", "arch")


@dataclass
class Bullet:
    label: str
    body: str


@dataclass
class Col:
    """two-col 슬라이드의 좌/우 박스."""
    heading: str
    bullets: list[Bullet] = field(default_factory=list)


@dataclass
class TableSpec:
    headers: list[str]
    rows: list[list[str]]
    note: str = ""


@dataclass
class Series:
    name: str
    values: list  # plan.md 표기 그대로: 숫자는 int/float, 그 외는 str


@dataclass
class ChartSpec:
    categories: list[str]
    series: list[Series]
    source: str = ""


@dataclass
class ArchGroup:
    name: str
    items: list[str]  # 박스 라벨 원본 (쉼표 나열 유지 — 문서 재구성 시에도 쉼표 유지)


@dataclass
class Slide:
    """plan.md의 슬라이드 항목 1개 (### N. ...)."""
    no: int                    # plan 전체 번호 (### N. 의 N)
    type: str                  # 영문 7종 (SLIDE_TYPES_KO_TO_EN 값)
    title: str                 # 태그를 제외한 슬라이드 제목
    docs: list[str] = field(default_factory=list)  # [문서: ...] 태그. 빈 리스트 = 전체 문서 (공통과 동일)
    source: str = ""           # 근거/출처 문자열 (한 글자 유지)
    message: str = ""          # 핵심문장 (cover/toc/closing)
    left: Col | None = None    # two-col
    right: Col | None = None   # two-col
    table: TableSpec | None = None
    chart: ChartSpec | None = None
    arch: list[ArchGroup] = field(default_factory=list)

    def is_content(self) -> bool:
        return self.type in CONTENT_TYPES


@dataclass
class Plan:
    """plan.md 파싱 결과. SSOT(DB Plan 레코드)의 메모리 표현."""
    title: str = ""            # H1 (자유 텍스트)
    docs: list[str] = field(default_factory=list)   # 메타 `산출 문서` (없으면 ["제안서"])
    purpose: str = ""
    audience: str = ""
    length: str = ""           # 예상 분량
    deadline: str = ""         # 제출 시한 (메타에 있을 때)
    key_messages: list[str] = field(default_factory=list)  # 정확히 3개
    slides: list[Slide] = field(default_factory=list)


class PlanError(ValueError):
    """plan.md 포맷 위반 (파싱 불가·규칙 위반)."""