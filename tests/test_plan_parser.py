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


# ------------------------------------------------------- 개발설계서 설계 결정 샘플

@pytest.fixture(scope="module")
def design_plan():
    return parse_plan_file(FIX / "plan.design.sample.md")


def test_design_plan_meta_and_docs(design_plan):
    assert design_plan.docs == ["제안서", "개발설계서"]
    assert "설계 결정" in design_plan.purpose
    assert len(design_plan.key_messages) == 3


def test_design_decision_tables_verbatim(design_plan):
    """설계 결정표(항목|선택|이유|상태) — 셀 원문 보존, (미확정) 셀 포함 (수치 무결성)."""
    s = slide_by_no(design_plan, 7)
    assert s.table.headers == ["항목", "선택", "이유", "상태"]
    assert s.table.rows == [
        ["언어", "Python 3.12", "팀 경험·라이브러리 풍부", "확정"],
        ["웹 프레임워크", "FastAPI", "비동기 지원·OpenAPI 자동화", "확정"],
        ["ORM", "SQLAlchemy 2.x", "비동기 세션 지원", "확정"],
        ["캐시", "Redis", "대안 인메모리 폴백은 성능 미달", "(미확정)"],
    ]
    api = slide_by_no(design_plan, 8)
    assert api.table.headers == ["항목", "방식", "규약", "상태"]
    assert all(any("(미확정)" in c for c in row) is False for row in api.table.rows)


def test_design_two_col_constraints(design_plan):
    s = slide_by_no(design_plan, 9)
    assert s.left.heading == "제약"
    assert s.right.heading == "비목표"
    assert (s.left.bullets[0].label, s.left.bullets[0].body) == (
        "단일 DB", "SQLite 단일 방언 (WAL + busy_timeout)")
    assert s.right.bullets[0].label == "인증"


def test_design_arch_shared_doc_tag(design_plan):
    s = slide_by_no(design_plan, 6)
    assert s.type == "arch"
    assert s.docs == ["제안서", "개발설계서"]  # 복수 소속 + 태그
    assert [(g.name, g.items) for g in s.arch] == [
        ("사용자 계층", ["웹 UI", "인터뷰 채팅 화면"]),
        ("서비스 계층", ["REST API", "작업 큐 워커"]),
        ("데이터 계층", ["SQLite (WAL)", "워크스페이스 파일"]),
    ]


def test_rejects_arch_over_6_layers():
    """구성 슬라이드 한도(계층 최대 6) — 인터뷰 프롬프트 개발설계서 구성 가이드가
    인용한 서버 검증을 테스트로 고정한다."""
    from planforge.plan import parse_plan_text

    layers = "\n".join(f"  - 계층{i} | 박스" for i in range(1, 8))
    text = (
        "# 설계 (구성 한도)\n\n"
        "## 핵심 메시지 (3개)\n1. a\n2. b\n3. c\n\n"
        "## 슬라이드 목록\n\n"
        f"### 1. [유형: 구성] 시스템 구성도\n- 구성:\n{layers}\n"
    )
    with pytest.raises(Exception, match="계층은 최대 6개"):
        parse_plan_text(text)


# ------------------------------------------------- 다중 문서 메타 교차검증 (계약)

def test_rejects_tagged_multidoc_without_meta_docs():
    """메타 '산출 문서' 누락 + 태그된 다중 문서 plan → PlanError. 슬라이드 태그가 정확해도
    디폴트 ["제안서"] 무음 치환은 derive가 나머지 문서 슬라이드를 버리는 사고 경로다.
    (실세션 수업: 인터뷰에서 제안서+개발설계서 선택 → 슬라이드 태그 정상 → 메타 누락
    → 제안서 1종만 산출.)"""
    from planforge.plan import parse_plan_text
    text = PLAN.read_text(encoding="utf-8").replace("- 산출 문서: 제안서, 개발설계서\n", "")
    with pytest.raises(Exception, match="슬라이드 문서 태그 '개발설계서'가 메타 '산출 문서'"):
        parse_plan_text(text)


def test_rejects_tag_outside_meta_docs():
    """태그 어휘 불일치 — 슬라이드 [문서: ...] 태그가 메타 '산출 문서'에 정의되지 않은
    문서를 가리키면 PlanError (검수에서만 잡히던 것을 파싱 시점으로 앞당김)."""
    from planforge.plan import parse_plan_text
    text = PLAN.read_text(encoding="utf-8").replace(
        "- 산출 문서: 제안서, 개발설계서", "- 산출 문서: 제안서")
    with pytest.raises(Exception, match="개발설계서"):
        parse_plan_text(text)


def test_rejects_multi_docs_without_tagged_slides():
    """메타가 복수 문서인데 [문서: ...] 태그 슬라이드가 하나도 없으면 PlanError —
    문서별 표지·목차·마무리 별도 태그 계약의 파서 수준 최소 강제."""
    from planforge.plan import parse_plan_text
    text = (
        "# 기획 (태그 누락)\n\n"
        "## 메타\n- 산출 문서: 제안서, 개발설계서\n- 목적: x\n"
        "\n## 핵심 메시지 (3개)\n1. a\n2. b\n3. c\n\n"
        "## 슬라이드 목록\n\n"
        "### 1. [유형: 표지] 표지\n- 핵심문장: 표지다\n"
    )
    with pytest.raises(Exception, match="태그 슬라이드가 없습니다"):
        parse_plan_text(text)


def test_default_single_doc_still_works_without_meta():
    """하위호환 — 메타 누락 + 태그 없는 단일 문서 plan은 기존 동작 유지 (docs=["제안서"])."""
    from planforge.plan import parse_plan_text
    text = (
        "# 기획 (단일 문서)\n\n"
        "## 핵심 메시지 (3개)\n1. a\n2. b\n3. c\n\n"
        "## 슬라이드 목록\n\n"
        "### 1. [유형: 표지] 표지\n- 핵심문장: 표지다\n"
    )
    plan = parse_plan_text(text)
    assert plan.docs == ["제안서"]


def test_meta_and_tag_accept_comma_and_plus_separators():
    """구분자 정규화 — 메타는 쉼표가 관례, 태그는 +가 관례이지만 둘 다 실수를 흡수한다."""
    from planforge.plan import parse_plan_text
    base = PLAN.read_text(encoding="utf-8")
    meta_plus = parse_plan_text(base.replace(
        "- 산출 문서: 제안서, 개발설계서", "- 산출 문서: 제안서+개발설계서"))
    assert meta_plus.docs == ["제안서", "개발설계서"]
    tag_comma = parse_plan_text(base.replace(
        "[문서: 제안서+개발설계서]", "[문서: 제안서, 개발설계서]"))
    assert slide_by_no(tag_comma, 6).docs == ["제안서", "개발설계서"]