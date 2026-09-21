# -*- coding: utf-8 -*-
"""numcheck(수치 무결성 대조) 단위 테스트 — 원칙 3 상시 실행용."""
import pytest

from planforge.numcheck import check_report, check_slides, has_red, numeric_tokens
from planforge.plan.model import ChartSpec, Series, Slide, TableSpec


def make_plan_slides():
    return [
        Slide(no=1, type="cover", title="업무 자동화 도입 제안",
              message="주 11.5시간 절감", source="interview-log [2026-09-09] 효과 수치 정책"),
        Slide(no=2, type="table", title="업무 시간 비교",
              table=TableSpec(
                  headers=["항목", "현재", "제안 후"],
                  rows=[["보고 작성 (주)", "10시간", "2시간"],
                        ["오류 건수 (월)", "3건", "0건"]],
                  note="근거/출처: interview-log [2026-09-09] 효과 수치 정책"),
              source="근거/출처: interview-log [2026-09-09] 효과 수치 정책"),
        Slide(no=3, type="chart", title="소요 시간 추이",
              chart=ChartSpec(categories=["2024", "2025", "2026(제안)"],
                              series=[Series(name="소요 시간(h)", values=[14, 14, 2.5])],
                              source="출처: (미확정 - 샘플 데이터)"),
              source="출처: (미확정 - 샘플 데이터)"),
    ]


def make_slides_doc():
    return {
        "meta": {"title": "업무 자동화 도입 제안"},
        "slides": [
            {"type": "cover", "title": "업무 자동화 도입 제안",
             "subtitle": "주 11.5시간 절감"},
            {"type": "table", "title": "업무 시간 비교",
             "table": {"headers": ["항목", "현재", "제안 후"],
                       "rows": [["보고 작성 (주)", "10시간", "2시간"],
                                ["오류 건수 (월)", "3건", "0건"]],
                       "note": "근거/출처: interview-log [2026-09-09] 효과 수치 정책"}},
            {"type": "chart", "title": "소요 시간 추이",
             "chart": {"categories": ["2024", "2025", "2026(제안)"],
                       "series": [{"name": "소요 시간(h)", "values": [14, 14, 2.5]}],
                       "source": "출처: (미확정 - 샘플 데이터)"}},
        ],
    }


KEY_MESSAGES = ["반복 보고 업무를 자동화해 주 11.5시간을 되찾는다",
                "부서별 양식 상이를 표준 파이프라인으로 흡수한다",
                "시범 도입으로 효과를 먼저 검증한 뒤 확장한다"]


def test_clean_pair_has_no_findings():
    findings = check_slides(make_plan_slides(), KEY_MESSAGES, make_slides_doc())
    assert findings == []


def test_numeric_distortion_is_red():
    doc = make_slides_doc()
    doc["slides"][1]["table"]["rows"][0][2] = "3시간"  # 2시간 → 3시간 왜곡 (수용 기준 3)
    doc["slides"][1]["table"]["rows"][1][2] = "0건"    # 보상: 3건→0건은 유지
    findings = check_slides(make_plan_slides(), KEY_MESSAGES, doc)
    assert any(f.code == "numeric-missing" and "2" in f.message for f in findings)
    assert any(f.code == "numeric-extra" and "3" in f.message for f in findings)


def test_chart_value_distortion_is_red():
    doc = make_slides_doc()
    doc["slides"][2]["chart"]["series"][0]["values"] = [14, 14, 2.6]
    findings = check_slides(make_plan_slides(), KEY_MESSAGES, doc)
    assert any(f.code == "numeric-extra" and "2.6" in f.message for f in findings)
    assert any(f.code == "numeric-missing" and "2.5" in f.message for f in findings)


def test_unconfirmed_marker_must_survive():
    doc = make_slides_doc()
    doc["slides"][2]["chart"]["source"] = "출처: 샘플 데이터"  # (미확정) 삭제
    findings = check_slides(make_plan_slides(), KEY_MESSAGES, doc)
    assert any(f.code == "unconfirmed-lost" for f in findings)


def test_unconfirmed_marker_must_not_appear_without_plan():
    doc = make_slides_doc()
    doc["slides"][1]["table"]["rows"][0][2] = "2시간 (미확정)"
    findings = check_slides(make_plan_slides(), KEY_MESSAGES, doc)
    assert any(f.code == "unconfirmed-extra" for f in findings)


def test_report_source_string_must_survive():
    # slides.json에는 표지 근거를 담을 슬롯이 없으므로 source-missing은 report 대조에서만 검사한다
    plan_slides = make_plan_slides()
    report = {
        "meta": {"title": "제안"},
        "sections": [
            {"type": "section", "no": "1", "title": "비교",
             "blocks": [{"kind": "table", "heading": "표",
                         "headers": ["항목", "현재", "제안 후"],
                         "rows": [["보고 작성 (주)", "10시간", "2시간"]]}],
             "source": ""},  # 근거/출처 누락
        ],
    }
    findings = check_report(plan_slides, KEY_MESSAGES, report)
    assert any(f.code == "source-missing" for f in findings)
    assert any(f.code == "numeric-missing" for f in findings)  # 유실 수치도 탐지


def test_slide_count_mismatch_is_red():
    doc = make_slides_doc()
    doc["slides"] = doc["slides"][:2]
    findings = check_slides(make_plan_slides(), KEY_MESSAGES, doc)
    assert any(f.code == "structure" and "슬라이드 수" in f.message for f in findings)


def test_report_global_numeric_check():
    plan_slides = make_plan_slides()
    report = {
        "meta": {"title": "업무 자동화 도입 제안"},
        "sections": [
            {"type": "header", "title": "업무 자동화 도입 제안", "subtitle": "주 11.5시간 절감"},
            {"type": "overview", "title": "개요", "items": [
                {"no": "01", "label": "기대 효과", "body": "주 11.5시간의 업무 시간을 절감한다"}]},
            {"type": "section", "no": "1", "title": "업무 시간 비교",
             "blocks": [{"kind": "table", "heading": "도입 전후 비교",
                         "headers": ["항목", "현재", "제안 후"],
                         "rows": [["보고 작성 (주)", "10시간", "2시간"],
                                  ["오류 건수 (월)", "3건", "0건"]]}],
             "source": "근거/출처: interview-log [2026-09-09] 효과 수치 정책"},
            {"type": "section", "no": "2", "title": "소요 시간 추이",
             "blocks": [{"kind": "data", "heading": "추이",
                         "categories": ["2024", "2025", "2026(제안)"],
                         "series": [{"name": "소요 시간(h)", "values": [14, 14, 2.5]}],
                         "unit": "h"}],
             "source": "출처: (미확정 - 샘플 데이터)"},
        ],
    }
    assert check_report(plan_slides, KEY_MESSAGES, report) == []


def test_report_fabrication_is_red():
    plan_slides = make_plan_slides()
    report = {
        "meta": {"title": "제안"},
        "sections": [
            {"type": "section", "no": "1", "title": "비교",
             "blocks": [{"kind": "prose", "heading": "해설",
                         "paragraphs": ["비용은 연 1억원이다"]}],  # plan에 없는 수치 창작
             "source": ""},
        ],
    }
    findings = check_report(plan_slides, KEY_MESSAGES, report)
    assert any(f.code == "numeric-extra" and "1억" not in f.message and "1" in f.message
               for f in findings)
    assert any(f.code == "numeric-missing" for f in findings)  # plan 수치 유실도 탐지


def test_report_repetition_is_yellow_not_red():
    """문서체 재구성의 자연스러운 수치 재진술은 yellow — 창작만 red."""
    plan_slides = make_plan_slides()
    report = {
        "meta": {"title": "제안"},
        "sections": [
            {"type": "section", "no": "1", "title": "비교",
             "blocks": [{"kind": "prose", "heading": "해설",
                         "paragraphs": [
                             "현재 보고 작성에 주 10시간이 소요된다.",
                             "자동화 후에는 10시간이 2시간으로 줄어든다."]}],  # '10' 재진술 (초과 1회)
             "source": "근거/출처: interview-log [2026-09-09] 효과 수치 정책"},
        ],
    }
    findings = check_report(plan_slides, KEY_MESSAGES, report)
    rep = [f for f in findings if f.code == "numeric-extra" and f.severity == "yellow"]
    assert any("10" in f.message and "재진술" in f.message for f in rep)
    # '10'의 초과분이 red(창작)로 오분류되지 않는지 — 창작 판정은 test_report_fabrication_is_red
    assert not any(f.code == "numeric-extra" and f.severity == "red" and "10" in f.message
                   for f in findings)


def test_numeric_tokens_normalizes_commas_and_dates():
    assert numeric_tokens("1,000 POD, 일 500GB") == {"1000": 1, "500": 1}
    assert numeric_tokens("2026. 9. 2.") == {}            # 날짜 표기는 정규화로 제외
    assert numeric_tokens("2026-09-09 효과 수치") == {}     # 날짜 + 뒤따르는 자릿수 없는 토큰 정리