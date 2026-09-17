# -*- coding: utf-8 -*-
"""문서 태그 필터 + 골격 검증 테스트 (원칙 6·8, FR-3.2)."""
from pathlib import Path

import pytest

from reportagent.plan import Plan, Slide, filter_slides, parse_plan_file, validate_skeleton
from reportagent.plan.filter import SkeletonError

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def plan():
    return parse_plan_file(FIX / "plan.sample.md")


def test_filter_proposal(plan):
    filtered = filter_slides(plan.slides, "제안서")
    assert [s.no for s in filtered] == [1, 3, 5, 6, 8]


def test_filter_design_doc(plan):
    filtered = filter_slides(plan.slides, "개발설계서")
    assert [s.no for s in filtered] == [2, 4, 5, 6, 7, 9]


def test_skeleton_passes_for_both_docs(plan):
    for doc in ("제안서", "개발설계서"):
        validate_skeleton(filter_slides(plan.slides, doc))  # 예외 없음


def test_skeleton_fails_on_empty_filter(plan):
    with pytest.raises(SkeletonError, match="표지"):
        validate_skeleton(filter_slides(plan.slides, "존재하지않는문서"))


def test_skeleton_fails_when_toc_missing():
    slides = [
        Slide(no=1, type="cover", title="표지"),
        Slide(no=2, type="two-col", title="내용"),
        Slide(no=3, type="closing", title="마무리"),
    ]
    with pytest.raises(SkeletonError, match="목차"):
        validate_skeleton(slides)


def test_skeleton_fails_when_content_missing():
    slides = [
        Slide(no=1, type="cover", title="표지"),
        Slide(no=2, type="toc", title="목차"),
        Slide(no=3, type="closing", title="마무리"),
    ]
    with pytest.raises(SkeletonError, match="내용"):
        validate_skeleton(slides)


def test_single_doc_plan_defaults():
    """산출 문서 메타 없음 = 제안서 1개 (현행 동작). 태그 없는 슬라이드는 전체 문서 포함."""
    plan = Plan()
    plan.slides = [Slide(no=1, type="cover", title="t")]
    assert filter_slides(plan.slides, "제안서") == plan.slides
    assert filter_slides(plan.slides, "개발설계서") == plan.slides  # 태그 없음 = 전체 문서 포함