# -*- coding: utf-8 -*-
"""docloops 프레젠테이션 스키마 — openapi-typescript로 TS 타입 생성 (§3.1 계약 잠금).

ProjectOut(presentation)이 내장하므로 타 모듈 스키마에서 import되는 공개 계약 표면이다
(jobs.presentation.schemas JobOut 선례 — facade 다음으로 허용되는 표면).
"""
from __future__ import annotations

from pydantic import BaseModel

from ..application.service import doc_label


class DocLoopOut(BaseModel):
    doc_slug: str
    label: str  # doc_label(doc_slug) — 제안서 | UI·UX설계서 | 개발설계서
    status: str  # locked | active | done
    # plan 진행상황 — plans 행 역참조 파생값(SSOT는 plans 행, 루프 행에 캐시하지 않는다)
    plan_version: int | None = None
    plan_id: int | None = None

    @classmethod
    def from_row(cls, row, gen: object | None) -> "DocLoopOut":
        """루프 행 + 최신 plan 세대(plans 행 역참조 파생) → DocLoopOut 조립.

        projects/api.py의 기존 _docloop_out과 정확히 같은 값을 낸다 — 필드·순서·
        직렬화는 불변.
        """
        return cls(
            doc_slug=row.doc_slug, label=doc_label(row.doc_slug), status=str(row.status),
            plan_version=gen.version_no if gen else None,
            plan_id=gen.id if gen else None,
        )