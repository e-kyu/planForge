# -*- coding: utf-8 -*-
"""interview 프레젠테이션 스키마 — openapi-typescript로 TS 타입 생성 (§3.1 계약 잠금)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    phase: str
    round_no: int
    status: str
    pending_questions: list | None
    pending_facts: list | None
    pending_key_messages: list | None
    checklist: list | None
    key_messages_approved: bool
    hypothesis: dict | None
    error: str | None
    created_at: object


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    role: str
    kind: str
    content: str
    payload: dict | None
    created_at: object


class SessionCreate(BaseModel):
    pass


class TurnCreate(BaseModel):
    message: str


class AnswerItem(BaseModel):
    index: int                    # pending_questions의 인덱스
    option: int | None = None     # 선택지 인덱스
    free_text: str | None = None  # 서술형/기타 답변


class AnswersCreate(BaseModel):
    answers: list[AnswerItem]


class FactsConfirmCreate(BaseModel):
    approve: bool
    edits: list[dict] | None = None  # [{index, content?, source?}] — 사용자 수정분


class KeyMessagesCreate(BaseModel):
    approve: bool
    feedback: str | None = None