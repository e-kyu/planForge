# -*- coding: utf-8 -*-
"""plan 로딩 단일 권위 — 파싱 → 문서 선택 → 필터 → 골격 검증 → (미확정) 탐지.

CLI(parse·numcheck·derive)·Deriver·인터뷰 agent·plan revise가 같은 절차를 반복하던
것을 모은다. **검증 의미·순서·오류 문구는 호출자별 기존 계약 그대로**다:

- `strict_doc=False` (CLI): 미지정/알 수 없는 doc는 기존처럼 필터 결과가 비어
  골격 검증(`validate_skeleton`)에서 실패한다 (SkeletonError).
- `strict_doc=True` (Deriver): 문서 존재를 먼저 검사해 Deriver의 기존 문구
  `"문서 '{doc}'가 plan 메타 '산출 문서'(...)에 없습니다"`를 유지한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..common.const import UNCONFIRMED_PREFIX
from .filter import SkeletonError, filter_slides, validate_skeleton
from .model import Plan, PlanError, Slide
from .parser import parse_plan_file


@dataclass(frozen=True)
class PreparedPlan:
    """필터·골격 검증을 마친 plan — 파싱 결과를 두 번 해석하지 않기 위한 전달체."""
    plan: Plan
    doc: str | None
    slides: list[Slide]
    unconfirmed: list[int]


def prepare_plan(plan: Plan, doc: str | None = None, *,
                 strict_doc: bool = False) -> PreparedPlan:
    """파싱된 Plan → 대상 문서 필터·골격 검증·(미확정) 슬라이드 번호."""
    resolved = doc or plan.docs[0]
    if strict_doc and resolved not in plan.docs:
        raise PlanError(f"문서 '{resolved}'가 plan 메타 '산출 문서'({', '.join(plan.docs)})에 없습니다")
    slides = filter_slides(plan.slides, resolved)
    validate_skeleton(slides)  # 원칙 8 — 미달 시 중단
    unconfirmed = [s.no for s in slides
                   if UNCONFIRMED_PREFIX in (s.source or "")
                   or UNCONFIRMED_PREFIX in (s.message or "")]
    return PreparedPlan(plan=plan, doc=resolved, slides=slides, unconfirmed=unconfirmed)


def load_plan_for_doc(path: str | Path, doc: str | None = None, *,
                      strict_doc: bool = False) -> PreparedPlan:
    """plan.md 파일 → PreparedPlan (파싱은 parse_plan_file 단일 경로)."""
    return prepare_plan(parse_plan_file(path), doc, strict_doc=strict_doc)


def validate_each_doc(plan: Plan) -> None:
    """문서별 골격 검증만 담당한다 (원칙 8).

    실패한 문서를 알 수 있도록 `SkeletonError` 메시지 앞에 `문서 '{doc}': `를 붙인다 —
    호출자(인터뷰·plan revise)는 각자의 기존 래핑 문구만 유지하면 최종 문자열이 동일하다.
    """
    for doc in plan.docs:
        try:
            validate_skeleton(filter_slides(plan.slides, doc))
        except SkeletonError as e:
            raise SkeletonError(f"문서 '{doc}': {e}") from e
