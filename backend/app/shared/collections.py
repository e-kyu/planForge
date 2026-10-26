# -*- coding: utf-8 -*-
"""컬렉션 공용 헬퍼 — 모듈 간 복제된 조회 패턴.

latest_by_key는 "정렬된 행 목록에서 key별 첫 행" 패턴(plans 최신 세대 per-doc,
review 파생물 최신 per-(kind, doc))을 한 곳에 모은다. 정렬은 호출자가 보장한다 —
이 헬퍼는 입력 순서를 그대로 신뢰하고 첫 행만 채택한다.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

RowT = TypeVar("RowT")


def latest_by_key(rows: Iterable[RowT], key: Callable[[RowT], object]) -> dict:
    """key(row)별 **첫 행**만 채택한 dict — 입력 순서 유지(정렬은 호출자 소관)."""
    out: dict = {}
    for row in rows:
        k = key(row)
        if k not in out:
            out[k] = row
    return out
