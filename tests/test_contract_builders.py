# -*- coding: utf-8 -*-
"""계약 테스트 — 빌더 회귀 (legacy 샘플 4종 이식 fixture).

legacy 스모크 테스트(python scripts/build_ppt.py samples/...)의 이식판.
samples/*.sample.json은 스키마 계약 fixture로 잠근다 (수용 기준 6).
채번 규칙(원칙 5: 확장자별 독립 시퀀스, 무덮어쓰기)도 같이 잠근다.
"""
import json
from pathlib import Path

import pytest

from reportagent.builders import build_doc, build_ppt

FIX = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8-sig"))


def _write_workspace(tmp_path: Path, name: str) -> Path:
    """fixture를 work/ 레이아웃으로 복사 (output_name 제거 — 자동 채번 경로를 검증한다)."""
    doc = _load(name)
    doc["meta"].pop("output_name", None)
    jp = tmp_path / "work" / name
    jp.parent.mkdir(parents=True, exist_ok=True)
    jp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return jp


@pytest.fixture
def slides_json(tmp_path):
    return _write_workspace(tmp_path, "slides.sample.json")


@pytest.fixture
def slides_design_json(tmp_path):
    return _write_workspace(tmp_path, "slides.design.sample.json")


@pytest.fixture
def report_json(tmp_path):
    return _write_workspace(tmp_path, "report.sample.json")


@pytest.fixture
def report_design_json(tmp_path):
    return _write_workspace(tmp_path, "report.design.sample.json")


# ---------------------------------------------------------------- 빌드 성공 (4종 × 전 포맷)

def test_build_ppt_sample(slides_json, tmp_path):
    out = tmp_path / "output"
    build_ppt.build(str(slides_json), str(out))
    files = list(out.glob("*.pptx"))
    assert len(files) == 1 and "_v01.pptx" in files[0].name


def test_build_ppt_design_sample(slides_design_json, tmp_path):
    out = tmp_path / "output"
    build_ppt.build(str(slides_design_json), str(out))
    files = list(out.glob("*.pptx"))
    assert len(files) == 1 and "_v01.pptx" in files[0].name


@pytest.mark.parametrize("fmt", ["md", "html", "docx"])
def test_build_doc_sample(report_json, tmp_path, fmt):
    out = tmp_path / "output"
    build_doc.build(str(report_json), fmt, str(out))
    files = list(out.glob(f"*.{fmt}"))
    assert len(files) == 1 and f"_v01.{fmt}" in files[0].name


@pytest.mark.parametrize("fmt", ["md", "html", "docx"])
def test_build_doc_design_sample(report_design_json, tmp_path, fmt):
    out = tmp_path / "output"
    build_doc.build(str(report_design_json), fmt, str(out))
    files = list(out.glob(f"*.{fmt}"))
    assert len(files) == 1 and f"_v01.{fmt}" in files[0].name


# ---------------------------------------------------------------- 채번 규칙 (원칙 5)

def test_version_increments_never_overwrites(slides_json, tmp_path):
    out = tmp_path / "output"
    build_ppt.build(str(slides_json), str(out))
    first = next(out.glob("*.pptx")).read_bytes()
    build_ppt.build(str(slides_json), str(out))
    files = sorted(f.name for f in out.glob("*.pptx"))
    assert files[0].endswith("_v01.pptx") and files[1].endswith("_v02.pptx")
    assert next(out.glob("*_v01.pptx")).read_bytes() == first  # 기존 파일 불변


def test_extension_independent_sequences(report_json, slides_json, tmp_path):
    out = tmp_path / "output"
    build_doc.build(str(report_json), "md", str(out))
    build_doc.build(str(report_json), "md", str(out))
    build_ppt.build(str(slides_json), str(out))
    # pptx v01과 md v02가 공존 — 확장자별 독립 시퀀스 (수용 기준 5)
    assert next(out.glob("*_v01.pptx")) is not None
    assert next(out.glob("*_v02.md")) is not None


# ---------------------------------------------------------------- 스키마 검증 (validate)

def test_validate_rejects_unknown_type(tmp_path):
    bad = {"meta": {"title": "제목"}, "slides": [{"type": "unknown", "title": "x"}]}
    jp = tmp_path / "bad.json"
    jp.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="알 수 없는 유형"):
        build_ppt.build(str(jp), str(tmp_path / "out"))


def test_validate_rejects_missing_required_key(tmp_path):
    bad = {"meta": {"title": "제목"}, "slides": [{"type": "table", "title": "x"}]}  # table 키 누락
    jp = tmp_path / "bad.json"
    jp.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="필수 키 누락"):
        build_ppt.build(str(jp), str(tmp_path / "out"))


def test_validate_rejects_row_longer_than_headers(tmp_path):
    bad = {"meta": {"title": "제목"},
           "slides": [{"type": "table", "title": "x",
                       "table": {"headers": ["a"], "rows": [["1", "2"]]}}]}
    jp = tmp_path / "bad.json"
    jp.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="셀 수"):
        build_ppt.build(str(jp), str(tmp_path / "out"))


def test_build_doc_rejects_unknown_format(report_json, tmp_path):
    with pytest.raises(ValueError, match="알 수 없는 포맷"):
        build_doc.build(str(report_json), "pdf", str(tmp_path / "out"))