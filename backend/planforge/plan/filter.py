# -*- coding: utf-8 -*-
"""문서 태그 필터 + 골격 검증 (원칙 6·8).

- 문서 태그: 슬라이드에 `[문서: 제안서+개발설계서]` — 태그 없음 = 전체 문서 포함, `[문서: 공통]`과 동일.
- 골격 검증: 필터 결과에 표지·목차·마무리가 각 1개 이상, 내용 슬라이드 1개 이상 — 미달 시 중단.
"""
from __future__ import annotations

from .model import Plan, Slide


class SkeletonError(ValueError):
    """골격 검증 미달 — 파생물 생성을 중단해야 한다 (원칙 8)."""


def doc_names(plan: Plan) -> list[str]:
    """plan의 산출 문서 목록 (메타 항목 없으면 ["제안서"])."""
    return plan.docs or ["제안서"]


def filter_slides(slides: list[Slide], doc_name: str) -> list[Slide]:
    """대상 문서가 속한 슬라이드만 추린다. 태그 없음·[문서: 공통]은 전체 문서 포함."""
    return [s for s in slides if not s.docs or doc_name in s.docs]


def validate_skeleton(filtered: list[Slide]) -> None:
    """표지·목차·마무리·내용 각 1개 이상 검증. 미달 시 SkeletonError (생성 중단)."""
    types = [s.type for s in filtered]
    missing = []
    for label, t in (("표지", "cover"), ("목차", "toc"), ("마무리", "closing")):
        if types.count(t) < 1:
            missing.append(label)
    if not any(s.is_content() for s in filtered):
        missing.append("내용(2단/표/차트/구성)")
    if missing:
        raise SkeletonError(
            "골격 검증 미달 — 다음 슬라이드가 최소 1개씩 없어 생성을 중단합니다: "
            + ", ".join(missing)
            + " (plan.md 수정 필요)")