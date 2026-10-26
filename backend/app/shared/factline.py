# -*- coding: utf-8 -*-
"""팩트 한 줄 표기 — interview-log·압축 컨텍스트·검수 컨텍스트 공용 형식.

기존 세 곳(compact.fact_line · agent 팩트 라인 · review_agent 팩트 라인)이 같은
문자열 형식을 각자 조립한다. 이 헬퍼는 그 형식을 한 곳에 고정한다 — 날짜·출처
표기는 legacy 규약(원칙 3: 수치·출처 문자열 무변형)이다.
"""
from __future__ import annotations

from datetime import date as _date
from datetime import datetime as _datetime


def format_fact_line(date, content: str, source: str, *,
                     marker: str = "", bullet: bool = False) -> str:
    """`"[{date}] {content} (출처: {source})"` — marker는 뒤에, bullet은 앞에 붙인다.

    - date가 date/datetime이면 isoformat(), 문자열이면 그대로 쓴다.
    - marker가 있으면 `" {marker}"`를 뒤에 붙인다 (compact.fact_line 동작).
    - bullet=True면 `"- "` 접두사를 붙인다 (agent 컨텍스트·review_agent 형식).
    """
    date_text = date.isoformat() if isinstance(date, (_date, _datetime)) else str(date)
    line = f"[{date_text}] {content} (출처: {source})"
    if marker:
        line = f"{line} {marker}".strip()
    if bullet:
        line = "- " + line
    return line
