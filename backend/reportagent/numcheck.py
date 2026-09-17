# -*- coding: utf-8 -*-
"""수치 무결성 대조 검증 (원칙 3, FR-4.1의 기계적 대조 부분).

plan ↔ 파생물(slides.json/report.json)에서:
- 수치·표·차트 데이터가 한 글자도 다르지 않게 복사됐는지 (숫자 토큰 다중집합 대조)
- (미확정) 표기가 파생물에서 사라지지 않았는지 / plan에 없는데 추가되지 않았는지
- 근거/출처 문자열이 파생물에 그대로 있는지 (괄호 주석 `(해당 문서 ...)` 제외)
- slides.json: 슬라이드 수·유형·제목 정합 (plan 필터 결과 ↔ 파생물 1:1)

수치 풀에서는 근거/출처·캡션(source/note 키)을 제외한다 — 그 안의 날짜류 표기는
콘텐츠 수치가 아니며, 근거 유실은 별도 규칙(source-missing)으로 잡기 때문.
문장체 재구성(개조식→서술형)은 문서 전체 단위 대조로 허용한다 (report.json).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from .plan.model import Slide
from .plan.parser import parse_toc_items

_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
UNCONFIRMED = "(미확정"  # "(미확정)"·"(미확정 - 사유)" 변형을 모두 잡는다
_SKIP_KEYS = {"source", "note"}          # 근거/출처·캡션 — 수치 풀 제외 (별도 규칙으로 대조)
_RENUMBER_KEYS = {"no", "label"}         # 재채번 구조 번호 (섹션 no·목차 라벨 01..NN)


@dataclass
class Finding:
    code: str      # numeric-missing | numeric-extra | unconfirmed-lost | unconfirmed-extra | source-missing | structure
    severity: str  # "red" | "yellow"
    where: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.where}: {self.message}"


# ---------------------------------------------------------------- 토큰 추출

def numeric_tokens(text: str) -> Counter:
    """텍스트에서 수치 토큰을 추출한다. 콤마 자릿수 구분("1,000")은 정규화해 비교한다."""
    return Counter(t.replace(",", "") for t in _NUM_RE.findall(text))


def _fmt_num(v) -> str:
    """JSON 수치 → 토큰 문자열 (14 → "14", 2.5 → "2.5")."""
    return str(v)


def _iter_strings(obj, skip_keys: frozenset = frozenset()) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k not in skip_keys:
                yield from _iter_strings(v, skip_keys)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_strings(v, skip_keys)


def _iter_numbers(obj, skip_keys: frozenset = frozenset()) -> Iterable[str]:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        yield _fmt_num(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k not in skip_keys:
                yield from _iter_numbers(v, skip_keys)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_numbers(v, skip_keys)


def _slide_content_strings(s: Slide) -> Iterable[str]:
    """plan Slide의 콘텐츠 텍스트 (근거/출처 제외).

    목차 슬라이드의 핵심문장('01 현황 / 02 ...')은 라벨 번호가 재채번 대상이라
    본문 텍스트만 수치 풀에 넣는다."""
    yield s.title
    if s.message:
        if s.type == "toc":
            for b in parse_toc_items(s.message):
                yield b.body
        else:
            yield s.message
    for col in (s.left, s.right):
        if col is not None:
            yield col.heading
            for b in col.bullets:
                yield b.label
                yield b.body
    if s.table is not None:
        yield from s.table.headers
        for row in s.table.rows:
            for c in row:
                yield str(c)
    if s.chart is not None:
        yield from s.chart.categories
        for sr in s.chart.series:
            yield sr.name
    for g in s.arch:
        yield g.name
        for item in g.items:
            yield item


def _slide_numbers(s: Slide) -> Iterable[str]:
    """차트 수치 값 (문자열 값도 수치 토큰으로 추출)."""
    for sr in (s.chart.series if s.chart else []):
        for v in sr.values:
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                yield _fmt_num(v)
            elif isinstance(v, str):
                yield from numeric_tokens(v)


def _plan_tokens(slides: list[Slide], key_messages: list[str]) -> Counter:
    c: Counter = Counter()
    for s in slides:
        for t in _slide_content_strings(s):
            c.update(numeric_tokens(t))
        c.update(_slide_numbers(s))
    for km in key_messages:
        c.update(numeric_tokens(km))
    return c


def _doc_tokens(doc: dict) -> Counter:
    """report.json 문서 수치 풀 — 재채번 필드(no·label)도 제외한다."""
    c: Counter = Counter()
    for t in _iter_strings(doc, _SKIP_KEYS | _RENUMBER_KEYS):
        c.update(numeric_tokens(t))
    for n in _iter_numbers(doc, _SKIP_KEYS | _RENUMBER_KEYS):
        c.update([n])
    return c


def _diff(plan: Counter, derived: Counter, where: str, out: list[Finding]) -> None:
    missing = plan - derived   # plan에 있는데 파생물에 없음 (유실)
    extra = derived - plan     # 파생물에 새로 생김 (창작)
    for tok, n in sorted(missing.items()):
        out.append(Finding("numeric-missing", "red", where,
                           f"수치 '{tok}'가 plan에는 있으나 파생물에서 사라졌습니다 ({n}회)"))
    for tok, n in sorted(extra.items()):
        out.append(Finding("numeric-extra", "red", where,
                           f"수치 '{tok}'가 plan에 없는데 파생물에 추가되었습니다 ({n}회)"))


# ---------------------------------------------------------------- slides.json 대조

def check_slides(plan_slides: list[Slide], key_messages: list[str], slides_doc: dict | str) -> list[Finding]:
    """plan 필터 슬라이드 ↔ slides.json 1:1 대조."""
    if isinstance(slides_doc, str):
        slides_doc = json.loads(slides_doc)
    out: list[Finding] = []
    jslides = slides_doc.get("slides", [])
    if len(jslides) != len(plan_slides):
        out.append(Finding("structure", "red", "slides",
                           f"슬라이드 수 불일치: plan {len(plan_slides)}개 vs slides.json {len(jslides)}개"))
    for ps, js in zip(plan_slides, jslides):
        where = f"슬라이드 {ps.no} ({ps.type})"
        if js.get("type") != ps.type:
            out.append(Finding("structure", "red", where,
                               f"유형 불일치: plan '{ps.type}' vs slides.json '{js.get('type')}'"))
        if js.get("title") != ps.title:
            out.append(Finding("structure", "yellow", where,
                               f"제목 불일치: plan '{ps.title}' vs slides.json '{js.get('title')}'"))
        p_tokens: Counter = Counter()
        for t in _slide_content_strings(ps):
            p_tokens.update(numeric_tokens(t))
        p_tokens.update(_slide_numbers(ps))
        # 목차 슬라이드의 불릿 라벨(01..NN 재채번)은 구조 번호라 수치 풀에서 제외
        skip = _SKIP_KEYS | _RENUMBER_KEYS if js.get("type") == "toc" else _SKIP_KEYS
        j_tokens: Counter = Counter()
        for t in _iter_strings(js, skip):
            j_tokens.update(numeric_tokens(t))
        for n in _iter_numbers(js, skip):
            j_tokens.update([n])
        _diff(p_tokens, j_tokens, where, out)
        # (미확정) 전파 — 근거/출처·캡션 포함 전체 텍스트 기준
        p_unconf = UNCONFIRMED in (ps.source or "") or UNCONFIRMED in (ps.message or "")
        j_text = " ".join(_iter_strings(js))
        if p_unconf and UNCONFIRMED not in j_text:
            out.append(Finding("unconfirmed-lost", "red", where,
                               "plan의 (미확정) 표기가 파생물에서 사라졌습니다"))
        if not p_unconf and UNCONFIRMED in j_text:
            out.append(Finding("unconfirmed-extra", "red", where,
                               "plan에 (미확정)이 없는데 파생물에 추가되었습니다"))
        # 근거/출처 대조는 report.json 쪽에서만 한다 — slides.json에는 표지 등
        # 근거를 담을 슬롯이 없어 유실로 볼 수 없다 (table.note·chart.source는 캡션 역할).
    return out


# ---------------------------------------------------------------- report.json 대조

def check_report(plan_slides: list[Slide], key_messages: list[str], report_doc: dict | str) -> list[Finding]:
    """plan 필터 슬라이드 ↔ report.json 전체 문서 대조 (문서체 재구성 허용 — 수치만 대조)."""
    if isinstance(report_doc, str):
        report_doc = json.loads(report_doc)
    out: list[Finding] = []
    _diff(_plan_tokens(plan_slides, key_messages), _doc_tokens(report_doc), "문서 전체", out)

    r_text = " ".join(_iter_strings(report_doc))
    for ps in plan_slides:
        where = f"슬라이드 {ps.no} ({ps.type})"
        if (UNCONFIRMED in (ps.source or "") or UNCONFIRMED in (ps.message or "")) and UNCONFIRMED not in r_text:
            out.append(Finding("unconfirmed-lost", "red", where,
                               "plan의 (미확정) 표기가 문서 어디에도 남아있지 않습니다"))
        if ps.source and not ps.source.startswith("(") and ps.source not in r_text:
            out.append(Finding("source-missing", "yellow", where,
                               f"근거/출처 문자열이 문서에 없습니다: {ps.source[:50]}"))
    return out


def has_red(findings: list[Finding]) -> bool:
    return any(f.severity == "red" for f in findings)