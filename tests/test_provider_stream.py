# -*- coding: utf-8 -*-
"""provider.stream() 단위 테스트 — 텍스트 델타 + tool-call 델타 누적 (D9)."""
from __future__ import annotations

from types import SimpleNamespace as NS

from reportagent.llm import ProfileConfig, get_provider


def test_base_url_env_override(monkeypatch):
    """LLM_BASE_URL 환경변수가 프로바이더 기본값을 대체한다 (컨테이너 배포용)."""
    monkeypatch.setenv("LLM_BASE_URL", "http://ollama:11434/v1")
    p = get_provider(ProfileConfig(provider="ollama", model="test-model"))
    assert p._client.base_url.host == "ollama" and p._client.base_url.path == "/v1/"


def test_base_url_config_wins_over_env(monkeypatch):
    """config.json의 base_url이 LLM_BASE_URL 환경변수보다 우선한다."""
    monkeypatch.setenv("LLM_BASE_URL", "http://ollama:11434/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")  # openai 프로바이더는 키 존재 검사만 한다
    p = get_provider(ProfileConfig(provider="openai", model="m", base_url="http://x:1"))
    assert p._client.base_url.host == "x"


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


class _FakeStream:
    """SDK 스트림 래퍼 — provider.stream()의 finally에서 close()를 호출한다 (7fbe594)."""

    def __init__(self, events):
        self._it = iter(events)

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._it)

    def close(self):
        pass


def test_stream_yields_text_and_completed_tool_calls(monkeypatch):
    p = _provider()
    p._client = NS(chat=NS(completions=NS(
        create=lambda **kw: _FakeStream(_stream_events()))))
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
    p._client = NS(chat=NS(completions=NS(
        create=lambda **kw: _FakeStream(_stream_events()))))
    assert list(p.chat_stream([{"role": "user", "content": "hi"}])) == ["안녕", "하세요"]