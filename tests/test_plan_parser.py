# -*- coding: utf-8 -*-
"""plan.md 결정론 파서 계약 테스트 — plan.sample.md (문서 태그·유형별 표기법 포함)."""
from pathlib import Path

import pytest

from planforge.plan import parse_plan_file

FIX = Path(__file__).parent / "fixtures"
PLAN = FIX / "plan.sample.md"


@pytest.fixture(scope="module")
def plan():
    return parse_plan_file(PLAN)


def test_meta(plan):
    assert plan.title == "기획 (업무 자동화 — 제안·개발설계)"
    assert plan.docs == ["제안서", "개발설계서"]
    assert "제안서는 도입 승인 설득" in plan.purpose
    assert plan.length == "제안서 4장 / 개발설계서 4장"


def test_key_messages_exactly_three(plan):
    assert len(plan.key_messages) == 3
    assert plan.key_messages[0] == "반복 보고 업무를 자동화해 주 11.5시간을 되찾는다"


def test_slide_count_and_numbers(plan):
    assert [s.no for s in plan.slides] == [1, 2, 3, 4, 5, 6, 7, 8, 9]


def slide_by_no(plan, no):
    return next(s for s in plan.slides if s.no == no)


def test_type_tags(plan):
    assert slide_by_no(plan, 1).type == "cover"
    assert slide_by_no(plan, 3).type == "toc"
    assert slide_by_no(plan, 5).type == "two-col"
    assert slide_by_no(plan, 6).type == "arch"
    assert slide_by_no(plan, 7).type == "table"
    assert slide_by_no(plan, 8).type == "closing"


def test_doc_tags(plan):
    assert slide_by_no(plan, 1).docs == ["제안서"]
    assert slide_by_no(plan, 2).docs == ["개발설계서"]
    assert slide_by_no(plan, 5).docs == []            # 태그 없음 = 전체 문서
    assert slide_by_no(plan, 6).docs == ["제안서", "개발설계서"]  # 복수 소속 +


def test_two_col_notation(plan):
    s = slide_by_no(plan, 5)
    assert s.left.heading == "현황"
    assert [(b.label, b.body) for b in s.left.bullets] == [
        ("보고 작성", "주 10시간 수기 작성"),
        ("데이터 취합", "부서별 양식 상이로 수작업 취합"),
    ]
    assert s.right.heading == "문제점"
    assert s.right.bullets[1].label == "오류 위험"


def test_table_notation(plan):
    s = slide_by_no(plan, 7)
    assert s.table.headers == ["연동 대상", "방식", "주기", "데이터"]
    assert s.table.rows == [
        ["인사 시스템", "API", "일 1회", "조직·사원 정보"],
        ["결재 시스템", "파일 배치", "주 1회", "보고서 원본"],
    ]
    assert s.source.startswith("(미확정)")      # 근거 없는 수치 표기 원본 유지
    assert "개발팀 협의 필요" in s.source


def test_arch_notation(plan):
    s = slide_by_no(plan, 6)
    assert [(g.name, g.items) for g in s.arch] == [
        ("사용자 계층", ["보고 작성 화면", "관리자 화면"]),
        ("서비스 계층", ["보고 생성 서비스", "데이터 취합 서비스"]),
        ("데이터 계층", ["보고 DB", "템플릿 저장소"]),
    ]


def test_source_string_verbatim(plan):
    s = slide_by_no(plan, 1)
    assert s.source == "interview-log [2026-09-09] 효과 수치 정책 (샘플)"


def test_rejects_unknown_type():
    from planforge.plan import parse_plan_text
    text = PLAN.read_text(encoding="utf-8").replace("[유형: 표지]", "[유형: 서론]")
    with pytest.raises(Exception, match="알 수 없는 유형"):
        parse_plan_text(text)