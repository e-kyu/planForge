# -*- coding: utf-8 -*-
"""plan.md 결정론 파서.

LLM/코드 역할 분리(원칙 2)에 따라 파싱은 전부 결정론 코드가 한다.
이 파서는 골격 검증·태그 필터·numcheck 대조·LLM derive 입력 구성에 쓰인다.
파싱은 원본을 한 글자도 바꾸지 않는다 — 수치 무결성 대조의 기준점이 되기 때문.
"""
from __future__ import annotations

import re
from pathlib import Path

from .model import (
    SLIDE_TYPES_KO_TO_EN,
    ArchGroup,
    Bullet,
    ChartSpec,
    Col,
    Plan,
    PlanError,
    Series,
    Slide,
    TableSpec,
)

_H1_RE = re.compile(r"^# (.+)$")
_H2_RE = re.compile(r"^## (.+)$")
_H3_RE = re.compile(r"^### (\d+)\. (.+)$")
_KEY_MSG_RE = re.compile(r"^\d+\.\s+(.+)$")
_META_RE = re.compile(r"^(?:-\s+)?([^:：]+)[：:]?\s*(.*)$")  # "- 항목: 값" (전각 콜론 허용)
_BRACKET_RE = re.compile(r"\[([^\]]+)\]")

# 유형별 표기 헤더 불릿 (legacy 원문 "유형별 표기법" 이식 — 원문은 git 이력 참조)
_RE_COL = re.compile(r"^\s*(?:-\s+)?(좌|우)\s*\(([^)]*)\)[：:]?\s*(.*)$")
_RE_TABLE = re.compile(r"^\s*(?:-\s+)?표\s*[：:]\s*\[(.+)\]$")
_RE_CHART = re.compile(r"^\s*(?:-\s+)?차트\s*[：:]?\s*(.*)$")
_RE_ARCH = re.compile(r"^\s*(?:-\s+)?구성\s*[：:]?\s*(.*)$")
_RE_CATEGORY = re.compile(r"^범주\s*[：:]?\s*(.+)$")
_TOC_ITEM_RE = re.compile(r"^(?P<no>\d{1,3})\s+(?P<body>.+)$")


def parse_plan_text(text: str) -> Plan:
    """plan.md 전체 텍스트 → Plan. 포맷 위반은 PlanError."""
    text = text.replace("﻿", "")
    lines = text.splitlines()

    plan = Plan()
    section = None  # None | "meta" | "messages" | "slides"

    cur_slide: Slide | None = None
    cur_target: tuple[str, object] | None = None  # 진행 중인 유형별 표기 컨테이너

    for raw in lines:
        line = raw.rstrip()

        m = _H1_RE.match(line)
        if m and section is None:
            plan.title = m.group(1).strip()
            continue
        m = _H2_RE.match(line)
        if m:
            head = m.group(1).strip()
            if head.startswith("메타"):
                section = "meta"
            elif head.startswith("핵심 메시지"):
                section = "messages"
            elif head.startswith("슬라이드 목록"):
                section = "slides"
            else:
                section = None
            cur_slide = None
            cur_target = None
            continue

        if section == "meta":
            m = _META_RE.match(line)
            if m:
                key, val = m.group(1).strip(), m.group(2).strip()
                if key == "산출 문서":
                    plan.docs = [d.strip() for d in val.split(",") if d.strip()]
                elif key == "목적":
                    plan.purpose = val
                elif key == "청중":
                    plan.audience = val
                elif key == "예상 분량":
                    plan.length = val
                elif key in ("제출 시한", "시한"):
                    plan.deadline = val
            continue

        if section == "messages":
            m = _KEY_MSG_RE.match(line)
            if m:
                plan.key_messages.append(m.group(1).strip())
            continue

        if section == "slides":
            m = _H3_RE.match(line)
            if m:
                cur_slide = _parse_slide_head(int(m.group(1)), m.group(2))
                plan.slides.append(cur_slide)
                cur_target = None
                continue
            if cur_slide is None:
                if line.strip() and not line.strip().startswith(("<!--", "<!--")):
                    raise PlanError(f"슬라이드 목록 섹션에 ### 항목 밖의 내용이 있습니다: {line.strip()[:40]}")
                continue
            cur_target = _parse_slide_line(cur_slide, line, cur_target)
            continue

    _validate_plan(plan)
    return plan


def parse_plan_file(path: str | Path) -> Plan:
    return parse_plan_text(Path(path).read_text(encoding="utf-8-sig"))


# ---------------------------------------------------------------- 슬라이드 파싱

def _parse_slide_head(no: int, head: str) -> Slide:
    """'### N. [유형: X][문서: A+B] 제목' 해석."""
    docs: list[str] = []
    stype_ko = ""
    title = head.strip()
    for br in _BRACKET_RE.findall(head):
        br = br.strip()
        if br.startswith("유형:") or br.startswith("유형："):
            stype_ko = br[3:].strip()
            title = title.replace(f"[{br}]", "", 1)
        elif br.startswith("문서:") or br.startswith("문서："):
            names = br[3:].strip()
            if names and names != "공통":
                docs = [d.strip() for d in names.split("+") if d.strip()]
            title = title.replace(f"[{br}]", "", 1)
    if not stype_ko:
        raise PlanError(f"슬라이드 {no}: [유형: ...] 표기가 없습니다 (7종 표기 필수)")
    if stype_ko not in SLIDE_TYPES_KO_TO_EN:
        raise PlanError(f"슬라이드 {no}: 알 수 없는 유형 '{stype_ko}' (표지/목차/2단/표/차트/구성/마무리 중 하나)")
    return Slide(no=no, type=SLIDE_TYPES_KO_TO_EN[stype_ko], title=title.strip(), docs=docs)


def _parse_slide_line(slide: Slide, line: str, cur_target) -> tuple[str, object] | None:
    """슬라이드 본문 줄 1개를 해석한다. 새 cur_target을 반환한다 (유형별 표기 헤더 줄에서 설정)."""
    stripped = line.strip()
    if not stripped or stripped.startswith("<!--"):
        return cur_target
    if stripped.startswith("- "):  # 하위 데이터 행의 불릿 마커 제거 ('  - 라벨 | 값' 형식)
        stripped = stripped[2:].strip()
        if not stripped:
            return cur_target

    if not line.startswith((" ", "\t")):  # 최상위 불릿
        m2 = _RE_COL.match(line)
        m3 = _RE_TABLE.match(line)
        if m2:
            col = Col(heading=m2.group(2).strip())
            setattr(slide, "left" if m2.group(1) == "좌" else "right", col)
            return ("col", col)
        if m3:
            headers = [h.strip() for h in m3.group(1).split("|")]
            slide.table = TableSpec(headers=headers, rows=[])
            return ("table", slide.table)
        if _RE_CHART.match(line):
            slide.chart = ChartSpec(categories=[], series=[])
            return ("chart", slide.chart)
        if _RE_ARCH.match(line):
            return ("arch", slide.arch)
        m = _META_RE.match(line)
        if not m:
            raise PlanError(f"슬라이드 {slide.no}: 해석할 수 없는 줄입니다: {stripped[:40]}")
        key, val = m.group(1).strip(), m.group(2).strip()
        if key == "핵심문장":
            slide.message = val
        elif key in ("근거/출처", "출처"):
            slide.source = val
            if slide.type == "chart" and slide.chart is not None:
                slide.chart.source = val
        else:
            raise PlanError(f"슬라이드 {slide.no}: 해석할 수 없는 불릿입니다: {stripped[:40]}")
        return None

    # 하위 불릿 (유형별 표기의 데이터 행)
    if cur_target is None:
        raise PlanError(f"슬라이드 {slide.no}: 부모 불릿 없는 하위 항목입니다: {stripped[:40]}")
    kind, container = cur_target
    if kind == "col":
        parts = [p.strip() for p in stripped.split("|", 1)]
        if len(parts) != 2:
            raise PlanError(f"슬라이드 {slide.no} (2단): 하위 항목은 '라벨 | 설명' 형식이어야 합니다: {stripped[:40]}")
        container.bullets.append(Bullet(label=parts[0], body=parts[1]))
    elif kind == "table":
        cells = [c.strip() for c in stripped.split("|")]
        container.rows.append(cells)
    elif kind == "chart":
        m = _RE_CATEGORY.match(stripped)
        if m:
            container.categories = [c.strip() for c in m.group(1).split(",") if c.strip()]
        else:
            parts = [p.strip() for p in stripped.split("|", 1)]
            if len(parts) != 2:
                raise PlanError(f"슬라이드 {slide.no} (차트): '계열명 | 값, 값, ...' 또는 '범주: ...' 형식이어야 합니다: {stripped[:40]}")
            name, vals = parts
            container.series.append(
                Series(name=name, values=[_parse_num_token(v.strip()) for v in vals.split(",") if v.strip()]))
    elif kind == "arch":
        parts = [p.strip() for p in stripped.split("|", 1)]
        if len(parts) != 2:
            raise PlanError(f"슬라이드 {slide.no} (구성): '계층명 | 박스 라벨, ...' 형식이어야 합니다: {stripped[:40]}")
        items = [i.strip() for i in parts[1].split(",") if i.strip()]
        for item in items:
            if "," in item:
                raise PlanError(f"슬라이드 {slide.no} (구성): 박스 라벨 안에 쉼표를 쓸 수 없습니다: {item}")
        container.append(ArchGroup(name=parts[0], items=items))
    return cur_target


def _parse_num_token(tok: str):
    """plan.md 표기 그대로 보존: 정수 → int, 실수 → float, 그 외 → 원문 str."""
    if re.fullmatch(r"-?\d+", tok):
        return int(tok)
    if re.fullmatch(r"-?\d+\.\d+", tok):
        return float(tok)
    return tok


def parse_toc_items(message: str) -> list[Bullet]:
    """목차 핵심문장('01 현황 / 02 구성 / ...') → toc 불릿. 라벨 없으면 빈 라벨."""
    out = []
    for part in (p.strip() for p in message.split("/")):
        if not part:
            continue
        m = _TOC_ITEM_RE.match(part)
        if m:
            out.append(Bullet(label=m.group("no"), body=m.group("body").strip()))
        else:
            out.append(Bullet(label="", body=part))
    return out


# ---------------------------------------------------------------- 검증

def _validate_plan(plan: Plan) -> None:
    if not plan.title:
        raise PlanError("plan.md에 H1 제목이 없습니다")
    if not plan.slides:
        raise PlanError("plan.md에 슬라이드 목록이 없습니다")
    if not plan.docs:
        plan.docs = ["제안서"]  # 메타 항목 없음 = 제안서 1개 (현행 동작)
    if len(plan.key_messages) != 3:
        raise PlanError(f"핵심 메시지는 정확히 3개여야 합니다 (현재 {len(plan.key_messages)}개)")
    nos = [s.no for s in plan.slides]
    if nos != sorted(nos):
        raise PlanError("슬라이드 번호가 오름차순이 아닙니다")
    for s in plan.slides:
        if s.type == "two-col" and (s.left is None or s.right is None):
            raise PlanError(f"슬라이드 {s.no} (2단): 좌/우 박스가 모두 필요합니다")
        if s.type == "table" and (s.table is None or not s.table.headers):
            raise PlanError(f"슬라이드 {s.no} (표): '표: [헤더 | ...]' 표기가 필요합니다")
        if s.type == "table" and s.table is not None:
            for r, row in enumerate(s.table.rows, 1):
                if len(row) > len(s.table.headers):
                    raise PlanError(f"슬라이드 {s.no} (표): {r}행 셀 수가 헤더 수를 초과합니다")
        if s.type == "chart" and (s.chart is None or not s.chart.categories or not s.chart.series):
            raise PlanError(f"슬라이드 {s.no} (차트): '범주:'와 계열 데이터가 필요합니다")
        if s.type == "arch":
            if not s.arch:
                raise PlanError(f"슬라이드 {s.no} (구성): '구성:' 아래 계층 데이터가 필요합니다")
            if len(s.arch) > 6:
                raise PlanError(f"슬라이드 {s.no} (구성): 계층은 최대 6개입니다 (build_ppt.py 제한)")
            for g in s.arch:
                if len(g.items) > 6:
                    raise PlanError(f"슬라이드 {s.no} (구성): 계층당 구성요소는 최대 6개입니다 (build_ppt.py 제한)")