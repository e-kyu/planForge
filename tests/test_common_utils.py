# -*- coding: utf-8 -*-
"""common 유틸(io·const·slug·buildfs) 계약 테스트 — 동작·바이트 형식 불변."""
from __future__ import annotations

import json

from planforge.common.buildfs import (
    BUILD_VER_RE,
    format_build_filename,
    parse_build_filename,
)
from planforge.common.const import (
    DEFAULT_DOC_NAME,
    DERIVATIVE_KINDS,
    KEY_MESSAGE_COUNT,
    MAX_ARCH_GROUPS,
    MAX_ARCH_ITEMS,
    REPORT_FORMATS,
    UNCONFIRMED_EXACT,
    UNCONFIRMED_PREFIX,
)
from planforge.common.io import read_json, read_text_utf8, write_json
from planforge.common.slug import MAX_SLUG_LENGTH, SLUG_RE, is_valid_slug


# ---------------------------------------------------------------- io

def test_read_text_utf8_strips_bom(tmp_path):
    p = tmp_path / "bom.md"
    p.write_bytes("﻿가나다\n".encode("utf-8"))
    assert read_text_utf8(p) == "가나다\n"


def test_read_text_utf8_reads_plain_utf8(tmp_path):
    p = tmp_path / "plain.md"
    p.write_bytes("가나다\n".encode("utf-8"))
    assert read_text_utf8(p) == "가나다\n"


def test_read_json_accepts_bom_and_plain(tmp_path):
    obj = {"가": [1, 2.5, "x"], "b": None}
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    plain = tmp_path / "plain.json"
    plain.write_bytes(data)
    bom = tmp_path / "bom.json"
    bom.write_bytes(b"\xef\xbb\xbf" + data)
    assert read_json(plain) == obj
    assert read_json(bom) == obj


def test_write_json_bytes_exact(tmp_path):
    """기존 `Path.write_text(json.dumps(..., ensure_ascii=False, indent=2))`와 동일.

    개행은 플랫폼 규약(Windows CRLF)대로 기록되므로 텍스트로 비교한다 — trailing
    newline은 붙지 않고, 한글은 이스케이프되지 않는다.
    """
    obj = {"가": 1, "b": [1, 2]}
    p = write_json(tmp_path / "out.json", obj)
    text = p.read_text(encoding="utf-8")
    assert text == json.dumps(obj, ensure_ascii=False, indent=2)
    assert not text.endswith("\n")                     # trailing newline 금지
    assert "가".encode("utf-8") in p.read_bytes()      # ensure_ascii=False


def test_write_json_round_trip(tmp_path):
    obj = {"slides": [{"title": "표지", "values": [14, 2.5]}], "meta": {"title": "제목"}}
    p = write_json(tmp_path / "rt.json", obj)
    assert read_json(p) == obj


# ---------------------------------------------------------------- slug

def test_slug_valid_boundaries():
    assert is_valid_slug("a")
    assert is_valid_slug("proj-1")
    assert is_valid_slug("a" * MAX_SLUG_LENGTH)        # 64자 경계 포함
    assert MAX_SLUG_LENGTH == 64


def test_slug_invalid():
    assert not is_valid_slug("")
    assert not is_valid_slug("-leading")
    assert not is_valid_slug("Upper")
    assert not is_valid_slug("has_underscore")
    assert not is_valid_slug("한글")
    assert not is_valid_slug("a" * (MAX_SLUG_LENGTH + 1))


def test_slug_re_is_reexported_with_same_rule():
    assert SLUG_RE.fullmatch("proj-1")
    assert SLUG_RE.fullmatch("-leading") is None


# ---------------------------------------------------------------- const

def test_const_values():
    assert UNCONFIRMED_PREFIX == "(미확정"
    assert UNCONFIRMED_EXACT == "(미확정)"
    # prefix/exact 매칭 의미는 통합하지 않는다 — 판정 동작이 바뀐다
    assert UNCONFIRMED_PREFIX != UNCONFIRMED_EXACT
    assert DEFAULT_DOC_NAME == "제안서"
    assert DERIVATIVE_KINDS == ("slides", "report")
    assert REPORT_FORMATS == ("md", "html", "docx")
    assert KEY_MESSAGE_COUNT == 3
    assert MAX_ARCH_GROUPS == 6
    assert MAX_ARCH_ITEMS == 6


# ---------------------------------------------------------------- buildfs

def test_format_build_filename_zero_pads_version():
    assert format_build_filename("업무_자동화_도입_제안", 1, "md") == "업무_자동화_도입_제안_v01.md"
    assert format_build_filename("report", 12, "pptx") == "report_v12.pptx"


def test_format_parse_round_trip():
    for title, ver, ext in (("업무_자동화_도입_제안", 2, "md"),
                            ("report", 10, "pptx"),
                            ("a", 1, "html")):
        name = format_build_filename(title, ver, ext)
        assert parse_build_filename(name) == (title, ver, ext)


def test_parse_build_filename_lowercases_ext():
    assert parse_build_filename("report_v10.PPTX") == ("report", 10, "pptx")


def test_parse_build_filename_non_version_files():
    assert parse_build_filename("draft.md") is None
    assert parse_build_filename("draft_v01") is None    # 확장자 없음


def test_build_ver_re_matches_version_suffix():
    assert BUILD_VER_RE.search("업무_자동화_도입_제안_v02.md")
    assert BUILD_VER_RE.search("plain.md") is None
