# -*- coding: utf-8 -*-
"""provider.stream() 단위 테스트 — 텍스트 델타 + tool-call 델타 누적 (D9)."""
from __future__ import annotations

from types import SimpleNamespace as NS

from reportagent.llm import ProfileConfig, get_provider


def _provider():
    return get_provider(ProfileConfig(provider="ollama", model="test-model"))


def _stream_events():
    """openai SDK 스트림 이벤트 흉내 — 텍스트/툴콜 델타가 섞인 시나리오."""
    return [
        NS(choices=[NS(delta=NS(content="안녕", tool_calls=None))]),
        NS(choices=[NS(delta=NS(content="하세요", tool_calls=None))]),
        NS(choices=[NS(delta=NS(content=None, tool_calls=[
            NS(index=0, function=NS(name="ask_", arguments=None))]))]),
        NS(choices=[NS(delta=NS(content=None, tool_calls=[
            NS(index=0, function=NS(name="questions", arguments='{"questions":'))]))]),
        NS(choices=[NS(delta=NS(content=None, tool_calls=[
            NS(index=0, function=NS(name=None, arguments='[{"text":"q1"}]}'))]))]),
        NS(choices=[NS(delta=NS(content=None, tool_calls=[
            NS(index=1, function=NS(name="update_checklist", arguments='{"items":[]}'))]))]),
        NS(choices=[]),  # 빈 choices (keepalive 등)
    ]


def test_stream_yields_text_and_completed_tool_calls(monkeypatch):
    p = _provider()
    p._client = NS(chat=NS(completions=NS(create=lambda **kw: iter(_stream_events()))))
    events = list(p.stream([{"role": "user", "content": "hi"}]))

    texts = [e for e in events if e["type"] == "text"]
    assert [e["delta"] for e in texts] == ["안녕", "하세요"]

    calls = [e for e in events if e["type"] == "tool_call"]
    assert len(calls) == 2
    assert calls[0]["name"] == "ask_questions"
    assert calls[0]["arguments"] == {"questions": [{"text": "q1"}]}
    assert calls[1]["name"] == "update_checklist"


def test_chat_stream_remains_text_only(monkeypatch):
    """레거시 chat_stream은 텍스트만 — M1 호환 유지."""
    p = _provider()
    p._client = NS(chat=NS(completions=NS(create=lambda **kw: iter(_stream_events()))))
    assert list(p.chat_stream([{"role": "user", "content": "hi"}])) == ["안녕", "하세요"]