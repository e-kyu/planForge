# -*- coding: utf-8 -*-
"""derive 오케스트레이터 테스트 — 가짜 LLM을 주입해 결정론 파이프라인(검증·수치 게이트·재시도·기록)을 잠근다."""
import json
import sys
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from planforge.derive import Deriver, DeriveError, render_slides_text
from planforge.plan import filter_slides, parse_plan_file
from fakes import FakeLLM, correct_report_payload, correct_slides_payload, tool_call

FIX = Path(__file__).parent / "fixtures"
PLAN = FIX / "plan.sample.md"


# ---------------------------------------------------------------- 슬라이드 파생

def test_derive_slides_success(tmp_path):
    llm = FakeLLM([tool_call("write_slides_json", correct_slides_payload())])
    ws = tmp_path / "ws"
    res = Deriver(llm, ws).derive(PLAN, "slides", "제안서")
    assert res.slides_count == 5 and res.attempts == 1
    payload = json.loads(res.work_path.read_text(encoding="utf-8"))
    assert payload["meta"]["title"] == "업무 자동화 도입 제안"  # 결정론 보정: 표지 제목
    # SSOT: work/slides.json에 기록됨
    assert res.work_path == ws / "work" / "slides.json"


def test_derive_numeric_gate_retries_then_succeeds(tmp_path):
    bad = correct_slides_payload()
    bad["slides"][4]["bullets"][0]["body"] = "주 12시간 절감"  # 11.5 왜곡 주입 (수용 기준 3)
    llm = FakeLLM([
        tool_call("write_slides_json", bad),
        tool_call("write_slides_json", correct_slides_payload()),
    ])
    res = Deriver(llm, tmp_path).derive(PLAN, "slides", "제안서")
    assert res.attempts == 2
    # 재시도 피드백에 🔴 발견사항이 전달됐는지
    retry_user = llm.calls[1][-1]["content"]
    assert "수치 무결성 검증 실패" in retry_user and "12" in retry_user


def test_derive_schema_violation_retries():
    bad = {"meta": {"title": "제목"}, "slides": [{"type": "unknown", "title": "x"}]}
    llm = FakeLLM([
        tool_call("write_slides_json", bad),
        tool_call("write_slides_json", correct_slides_payload()),
    ])
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        res = Deriver(llm, td).derive(PLAN, "slides", "제안서")
        assert res.attempts == 2
        retry_user = llm.calls[1][-1]["content"]
        assert "스키마 검증 실패" in retry_user


def test_derive_gives_up_after_max_attempts():
    bad = correct_slides_payload()
    bad["slides"][4]["bullets"][0]["body"] = "주 12시간 절감"
    llm = FakeLLM([tool_call("write_slides_json", bad) for _ in range(3)])
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        with pytest.raises(DeriveError, match="수치 무결성"):
            Deriver(llm, td).derive(PLAN, "slides", "제안서")


# ---------------------------------------------------------------- 수치 리터럴 스냅 (LLM 정규화 교정)

CHART_PLAN = """# 제안서 기획 (차트 샘플)

## 메타
- 목적: 테스트
- 청중: 경영진
- 예상 분량: 4장

## 핵심 메시지 (3개)
1. 3분기 매출 12.4억 원
2. 4분기 목표 15.0억 원
3. 성장 지속

## 슬라이드 목록

### 1. [유형: 표지] 표지
- 핵심문장: 표지 문장
- 근거/출처: (미확정)

### 2. [유형: 목차] 목차
- 핵심문장: 01 매출 추이

### 3. [유형: 차트] 매출 추이
- 차트:
  - 범주: 3분기, 4분기
  - 매출(억 원) | 12.4, 15.0
- 근거/출처: 사내 집계

### 4. [유형: 마무리] 마무리
- 핵심문장: 마무리 문장
"""


def _chart_slides():
    from planforge.plan import filter_slides

    plan = parse_plan_file(_md_to_tmp(CHART_PLAN))
    return filter_slides(plan.slides, plan.docs[0])


def _md_to_tmp(md: str):
    import tempfile
    from pathlib import Path

    f = Path(tempfile.mkdtemp()) / "plan.md"
    f.write_text(md, encoding="utf-8")
    return f


def test_snap_literals_restores_plan_decimal_notation():
    """LLM이 15.0을 15로 정규화해도 결정론 스냅이 plan 표기(15.0)로 되돌린다."""
    deriver = Deriver(None, ".")
    slides = _chart_slides()
    payload = {"slides": [{"type": "chart", "title": "매출 추이",
                           "chart": {"categories": ["3분기", "4분기"],
                                     "series": [{"name": "매출(억 원)", "values": [12.4, 15]}]}}]}
    deriver._snap_literals(slides, payload)
    assert payload["slides"][0]["chart"]["series"][0]["values"] == [12.4, 15.0]


def test_snap_literals_leaves_unknown_values_untouched():
    """plan에 수치적으로 동일한 값이 없으면 건드리지 않는다 (창작 교정 아님)."""
    deriver = Deriver(None, ".")
    slides = _chart_slides()
    payload = {"slides": [{"type": "chart", "title": "매출 추이",
                           "chart": {"categories": ["3분기", "4분기"],
                                     "series": [{"name": "매출(억 원)", "values": [12.4, 20]}]}}]}
    deriver._snap_literals(slides, payload)
    assert payload["slides"][0]["chart"]["series"][0]["values"] == [12.4, 20]


def test_snap_literals_report_data_block():
    deriver = Deriver(None, ".")
    slides = _chart_slides()
    payload = {"sections": [{"type": "section", "title": "매출 추이",
                             "blocks": [{"kind": "data", "heading": "매출 추이",
                                         "categories": ["3분기", "4분기"],
                                         "series": [{"name": "매출(억 원)", "values": [15]}]}]}]}
    deriver._snap_literals(slides, payload)
    block = payload["sections"][0]["blocks"][0]
    assert block["series"][0]["values"] == [15.0]


# ---------------------------------------------------------------- 문서 파생 (문서체 재구성)

def test_derive_report_success_and_build(tmp_path):
    llm = FakeLLM([tool_call("write_report_json", correct_report_payload())])
    res = Deriver(llm, tmp_path).derive(PLAN, "report", "제안서")
    assert res.sections_count == 5 and res.attempts == 1
    outs = Deriver(llm, tmp_path).build("report", ("md",))
    md = [p for p in outs if p.suffix == ".md"]
    assert md and "_v01" in md[0].name
    text = md[0].read_text(encoding="utf-8")
    assert "11.5시간" in text and "10시간" in text  # 수치 유지


def test_derive_rejects_doc_not_in_plan(tmp_path):
    llm = FakeLLM([])
    from planforge.plan import PlanError
    with pytest.raises(PlanError, match="산출 문서"):
        Deriver(llm, tmp_path).derive(PLAN, "slides", "보고서")


def test_render_slides_text_verbatim():
    plan = parse_plan_file(PLAN)
    slides = filter_slides(plan.slides, "제안서")
    text = render_slides_text(plan, slides, "제안서")
    assert "주 11.5시간을 되찾는다" in text                     # 핵심 메시지 무변경
    assert "보고 작성 | 주 10시간 수기 작성" in text            # 2단 표기 무변경
    assert "사용자 계층 | 보고 작성 화면, 관리자 화면" in text   # 구성 표기 무변경
    assert "interview-log [2026-09-09] 효과 수치 정책 (샘플)" in text  # 근거 무변경


def test_render_slides_text_design_plan_verbatim():
    """설계 결정 샘플 — 결정표·(미확정)·구성 표기가 derive LLM 입력에 그대로 나온다."""
    design = FIX / "plan.design.sample.md"
    plan = parse_plan_file(design)
    slides = filter_slides(plan.slides, "개발설계서")
    text = render_slides_text(plan, slides, "개발설계서")
    assert "  - 언어 | Python 3.12 | 팀 경험·라이브러리 풍부 | 확정" in text   # 결정표 원문
    assert "  - 캐시 | Redis | 대안 인메모리 폴백은 성능 미달 | (미확정)" in text
    assert "  - 사용자 계층 | 웹 UI, 인터뷰 채팅 화면" in text                 # 구성 표기 무변경
    assert "설계 결정(아키텍처·스택·규약)의 확정" in text                      # 목적 무변경


# ---------------------------------------------------------------- provider 설정

def test_load_config_profiles():
    """config.example.json 로드 — ollama·openai·azure를 섞어 각 프로바이더 설정 형태를
    보여주는 예시(편차 13) 기준. "_"로 시작하는 설명 키는 무시돼야 통과한다."""
    from planforge.llm import load_config
    profiles = load_config(Path(__file__).parent.parent / "backend" / "planforge" / "config.example.json")
    assert set(profiles) == {"interview", "derive", "review", "plan_revise"}
    assert profiles["interview"].provider == "azure"
    assert profiles["derive"].model == "gpt-4.1"  # config.example.json 샘플 모델과 동기
    assert profiles["review"].provider == "ollama"
    assert profiles["review"].model == "gemma4:26b"
    assert profiles["plan_revise"].provider == "openai"
    assert profiles["plan_revise"].model == "gpt-4.1"  # plan_revise 프로필 로드 (review 폴백 버그 수정)


def test_provider_requires_model():
    from planforge.llm import ProfileConfig, get_provider
    with pytest.raises(ValueError, match="모델"):
        get_provider(ProfileConfig(provider="ollama", model=""))


def test_config_file_missing_message(tmp_path, monkeypatch):
    """config.json이 없으면 안내와 함께 exit 2 (cmd_derive 레벨)."""
    from planforge import __main__ as m
    ns = m.argparse.Namespace(plan=str(PLAN), workspace=str(tmp_path), kind="slides",
                              doc=None, fmts=None, no_build=True, allow_unconfirmed=False,
                              config=str(tmp_path / "none.json"))
    assert m.cmd_derive(ns) == 2


# ------------------------------------------------ 실행 설정(config.json) 기반 검증 (편차 13)

def _runtime_config_path():
    """실행 LLM 설정 경로 — PLANFORGE_CONFIG env > backend/planforge/config.json.

    app/shared/config.py가 쓰는 우선순위를 그대로 미러럴 — 테스트가 실제 런타임 설정을
    본다. PLANFORGE_CONFIG 주입으로 tmp config 기반 결정론 검증도 가능하다."""
    import os
    env = os.environ.get("PLANFORGE_CONFIG", "")
    if env:
        return Path(env)
    return Path(__file__).parent.parent / "backend" / "planforge" / "config.json"


def _verify_providers(path) -> tuple[list, list]:
    """실행 설정 각 프로필의 provider 생성을 네트워크 호출 없이 검증한다.

    model이 지정된 프로필만 생성하고, 미설정 프로필은 경고 후 생략하며, 생성 실패는
    예외를 삼켜 전부 수집한다(README 계약 "생성 실패는 전부 모아 보고").
    반환: (생성된 (프로필명, provider) 목록, 실패 문자열 목록).
    """
    from planforge.llm import get_provider, load_config

    created, failures = [], []
    for name, profile in load_config(path).items():
        if not profile.model:
            warnings.warn(f"config.json profiles.{name}: model 미설정 — 생략",
                          stacklevel=2)
            continue
        try:
            created.append((name, get_provider(profile)))
        except Exception as e:
            failures.append(f"  {name} ({profile.provider}/{profile.model}): {e}")
    return created, failures


def test_provider_from_config_json():
    """실행 설정 backend/planforge/config.json(gitignored) 기반 provider 생성 검증.

    파일이 있으면 model이 지정된 프로필만 실제 provider 생성을 검증한다(네트워크 호출
    없음). 생성 실패는 전부 모아 보고하고, 생성에 성공한 프로필은 자동 재시도 금지
    계약(max_retries=0 — azure 분기 포함)을 다시 잠근다."""
    path = _runtime_config_path()
    if not path.is_file():
        pytest.skip(f"실행 설정이 없다: {path} (config.example.json을 복사해 시작)")
    try:
        created, failures = _verify_providers(path)
    except Exception as e:  # JSON 파싱 실패 등 — 명확하게 보고
        pytest.fail(f"실행 설정 파싱 실패: {path} — {e}")
    if failures:
        pytest.fail(f"provider 생성 실패 ({path}):\n" + "\n".join(failures))
    for name, p in created:
        assert p._llm.max_retries == 0, f"{name}: 자동 재시도 금지 계약(max_retries=0) 위반"


def test_provider_config_verification_reports_failures(tmp_path, monkeypatch):
    """결정론: 검증은 오류를 모아 보고한다 — azure 프로필에 필수값(azure_endpoint·
    api_version·키)이 없으면 실패 1건에 한국어 안내가 담긴다."""
    for var in ("AZURE_OPENAI_ENDPOINT", "OPENAI_API_VERSION", "AZURE_OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)  # 실제 환경 변수에 의존하지 않는다
    cfg = tmp_path / "config.json"
    cfg.write_text('{"profiles": {"interview": '
                   '{"provider": "azure", "model": "dep-1"}}}', encoding="utf-8")
    monkeypatch.setenv("PLANFORGE_CONFIG", str(cfg))
    created, failures = _verify_providers(_runtime_config_path())
    assert created == []
    assert len(failures) == 1 and failures[0].startswith("  interview (azure/dep-1):")
    assert "azure_endpoint" in failures[0]  # 즉시 실패 — openai SDK TypeError 전에 한국어 안내


def test_provider_config_verification_warns_model_less(tmp_path, monkeypatch):
    """결정론: model 미설정 프로필은 경고 후 생략 — 실패로 보고하지 않는다."""
    cfg = tmp_path / "config.json"
    cfg.write_text('{"profiles": {"interview": {"provider": "ollama"}}}',
                   encoding="utf-8")
    monkeypatch.setenv("PLANFORGE_CONFIG", str(cfg))
    with pytest.warns(UserWarning, match="model 미설정"):
        created, failures = _verify_providers(_runtime_config_path())
    assert created == [] and failures == []


def test_real_llm_smoke_from_config_json():
    """PLANFORGE_LLM_SMOKE=1일 때만 실행하는 실호출 스모크 — 실행 설정의 model 지정
    프로필마다 실제 LLM을 호출해 전송 경로(엔드포인트·키·스트리밍·tool 요청 수용)를
    확인한다. 실호출이라 비용·수십 초가 든다(README 계약: 평상 pytest는 스킵).

    실행 (PowerShell): $env:PLANFORGE_LLM_SMOKE = "1";
        pytest tests/test_derive.py::test_real_llm_smoke_from_config_json -v -rs
    """
    import os
    if os.environ.get("PLANFORGE_LLM_SMOKE", "") != "1":
        pytest.skip("실호출 스모크는 PLANFORGE_LLM_SMOKE=1 환경변수로만 실행한다")
    path = _runtime_config_path()
    if not path.is_file():
        pytest.skip(f"실행 설정이 없다: {path} (config.example.json을 복사해 시작)")
    from planforge.llm import get_provider, load_config

    profiles = {n: p for n, p in load_config(path).items() if p.model}
    if not profiles:
        pytest.skip("model이 지정된 프로필이 없다 — 검증 대상 없음")
    # tool probe: 게이트웨이가 tool 필드 서식을 거부해 400 내는 경우를 잡는 목적 —
    # 툴 호출 강제 없이 응답의 구조적 계약만 확인한다.
    probe_tool = [{"type": "function", "function": {
        "name": "noop", "description": "호출하지 않는 프로브",
        "parameters": {"type": "object", "properties": {}}}}]
    failures = []
    for name, profile in profiles.items():
        try:
            p = get_provider(profile)
            res = p.chat([{"role": "user", "content": "테스트 호출 — 한 단어로 대답하라"}])
            if not (isinstance(res.get("content"), str) and res["content"]):
                raise AssertionError(f"응답 계약 위반: {res!r}")
            if not isinstance(res.get("tool_calls"), list):
                raise AssertionError(f"tool_calls 계약 위반: {res!r}")
            res2 = p.chat([{"role": "user", "content": "테스트 호출 — 대답하라"}],
                          tools=probe_tool)
            if not (isinstance(res2.get("content"), (str, type(None)))
                    and isinstance(res2.get("tool_calls"), list)):
                raise AssertionError(f"tool probe 계약 위반: {res2!r}")
        except Exception as e:
            failures.append(f"  {name} ({profile.provider}/{profile.model}): {e}")
    if failures:
        pytest.fail("실호출 스모크 실패:\n" + "\n".join(failures))