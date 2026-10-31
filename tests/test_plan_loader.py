# -*- coding: utf-8 -*-
"""plan 로딩 단일 권위 테스트 — 준비(파싱·문서 선택·필터·골격·(미확정))와 Deriver 위임.

검증 의미·순서·오류 문구가 호출자별 기존 계약과 동일함을 잠근다.
"""
import json
from pathlib import Path

import pytest

from planforge.derive import Deriver
from planforge.plan import PlanError, SkeletonError, parse_plan_file
from planforge.plan.loader import load_plan_for_doc, prepare_plan, validate_each_doc
from fakes import FakeLLM, correct_report_payload, correct_slides_payload, tool_call

FIX = Path(__file__).parent / "fixtures"
PLAN = FIX / "plan.sample.md"
SKELETON_BAD = FIX / "plan.skeleton_bad.md"


# ---------------------------------------------------------------- 문서 선택·필터

def test_load_defaults_to_first_doc():
    """doc=None → plan.docs[0] (제안서) + 필터 결과·골격 통과."""
    prepared = load_plan_for_doc(PLAN)
    assert prepared.doc == "제안서"
    assert [s.no for s in prepared.slides] == [1, 3, 5, 6, 8]
    assert prepared.unconfirmed == []


def test_load_explicit_doc_and_unconfirmed_slides():
    """(미확정) 표기가 남은 슬라이드 번호를 로더가 함께 보고한다 (개발설계서 7번)."""
    prepared = load_plan_for_doc(PLAN, "개발설계서")
    assert prepared.doc == "개발설계서"
    assert [s.no for s in prepared.slides] == [2, 4, 5, 6, 7, 9]
    assert prepared.unconfirmed == [7]


def test_strict_doc_keeps_deriver_wording_for_unknown_doc():
    """strict_doc=True — Deriver의 문서 존재 검사 문구 그대로 (CLI보다 엄격)."""
    plan = parse_plan_file(PLAN)
    with pytest.raises(PlanError, match="산출 문서") as ei:
        prepare_plan(plan, "보고서", strict_doc=True)
    assert str(ei.value) == "문서 '보고서'가 plan 메타 '산출 문서'(제안서, 개발설계서)에 없습니다"


def test_non_strict_unknown_doc_fails_skeleton_like_cli():
    """strict_doc=False — 미지 doc는 필터가 비어 골격 검증에서 실패한다 (CLI 동작 보존)."""
    with pytest.raises(SkeletonError, match="표지"):
        load_plan_for_doc(PLAN, "보고서")


# ---------------------------------------------------------------- 골격 검증

def test_load_fails_when_skeleton_missing():
    with pytest.raises(SkeletonError) as ei:
        load_plan_for_doc(SKELETON_BAD)
    msg = str(ei.value)
    assert "필수 슬라이드가 최소 1개씩 없어" in msg
    assert "표지, 목차, 마무리" in msg        # 누락 유형 목록 원문 그대로
    assert "내용" not in msg                  # 표 슬라이드 1개는 있으므로 내용은 충족


def test_validate_each_doc_passes_for_all_docs():
    validate_each_doc(parse_plan_file(PLAN))  # 예외 없음 (문서 2종 모두 골격 통과)


def test_validate_each_doc_names_failing_doc():
    """호출자가 유지하는 래핑 문구가 문서명을 포함할 수 있도록 실패 문서를 붙인다."""
    plan = parse_plan_file(SKELETON_BAD)
    with pytest.raises(SkeletonError) as ei:
        validate_each_doc(plan)
    assert str(ei.value).startswith("문서 '제안서': 필수 슬라이드가 최소 1개씩 없어")


# ---------------------------------------------------------------- Deriver 위임

def test_derive_with_prepared_matches_parse_path(tmp_path):
    """prepared 경로가 파싱 경로와 동일한 DeriveResult를 낸다 — plan_path는 읽지 않는다."""
    res_parsed = Deriver(FakeLLM([tool_call("write_slides_json", correct_slides_payload())]),
                         tmp_path / "a").derive(PLAN, "slides", "제안서")

    prepared = load_plan_for_doc(PLAN, "제안서")
    res_prepared = Deriver(FakeLLM([tool_call("write_slides_json", correct_slides_payload())]),
                           tmp_path / "b").derive(tmp_path / "없는파일.md", "slides", "제안서",
                                                  prepared=prepared)

    assert res_prepared.doc == "제안서" == res_parsed.doc
    assert (res_prepared.slides_count, res_prepared.sections_count,
            res_prepared.attempts, res_prepared.unconfirmed) == (
        res_parsed.slides_count, res_parsed.sections_count,
        res_parsed.attempts, res_parsed.unconfirmed)
    assert res_prepared.findings == res_parsed.findings
    assert json.loads(res_prepared.work_path.read_text(encoding="utf-8")) == \
        json.loads(res_parsed.work_path.read_text(encoding="utf-8"))


def test_derive_resolves_doc_when_none(tmp_path):
    """doc=None이면 로더가 plan.docs[0]을 해석하고 res.doc에 그 값이 실린다."""
    llm = FakeLLM([tool_call("write_slides_json", correct_slides_payload())])
    res = Deriver(llm, tmp_path).derive(PLAN, "slides")
    assert res.doc == "제안서"


def test_derive_prepared_doc_wins_over_arg(tmp_path):
    """준비된 plan의 문서가 권위다 — 재파싱·재선택 없이 그대로 사용한다."""
    prepared = load_plan_for_doc(PLAN, "개발설계서")
    llm = FakeLLM([tool_call("write_report_json", correct_report_payload())])
    res = Deriver(llm, tmp_path).derive(PLAN, "report", "제안서", prepared=prepared)
    assert res.doc == "개발설계서"
