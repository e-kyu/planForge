# -*- coding: utf-8 -*-
"""SSE 이벤트 모델 — 인터뷰 스트림의 이벤트 타입과 페이로드 (D6).

모든 이벤트는 interview_messages 행으로도 영속되어 GET /messages?after=seq로 재접속 리플레이가 된다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from ..infrastructure.models import MessageKind, MessageRole


@dataclass
class Event:
    """SSE 이벤트 — name/payload는 동시에 interview_messages 행이 된다."""

    name: str  # token|questions|facts|key_messages|plan_draft|state|notice|error|done
    payload: dict
    role: MessageRole = MessageRole.EVENT
    kind: MessageKind = MessageKind.TEXT
    content: str = ""  # payload.text 본문이 있으면 이력 행의 content로 저장

    def sse(self) -> str:
        return f"event: {self.name}\ndata: {json.dumps(self.payload, ensure_ascii=False)}\n\n"


def token_event(text: str) -> Event:
    return Event(name="token", payload={"text": text}, role=MessageRole.ASSISTANT,
                 kind=MessageKind.TEXT, content=text)


def done_event(phase: str, session_status: str) -> Event:
    return Event(name="done", payload={"phase": phase, "session_status": session_status})


def state_event(phase: str, round_no: int, checklist: list | None) -> Event:
    return Event(name="state", payload={"phase": phase, "round_no": round_no,
                                        "checklist": checklist or []},
                 kind=MessageKind.STATE)


def notice_event(text: str, level: str = "info") -> Event:
    return Event(name="notice", payload={"level": level, "text": text},
                 kind=MessageKind.NOTICE, content=text)


def error_event(code: str, message: str) -> Event:
    return Event(name="error", payload={"code": code, "message": message},
                 kind=MessageKind.ERROR, content=message)