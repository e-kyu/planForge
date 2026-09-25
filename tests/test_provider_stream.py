# -*- coding: utf-8 -*-
"""provider.stream() 단위 테스트 — ChatOpenAI 어댑터 계약 (편차 10).

외부 계약은 기존과 동일: text/tool_call dict 이벤트, 다청크 tool-call 조립,
deadline 중단, base_url 우선순위. fake ChatOpenAI(p._llm)로 검증한다.
"""
from __future__ import annotations

import pytest
from langchain_core.messages import (AIMessage, AIMessageChunk, HumanMessage,
                                     SystemMessage, ToolMessage)

import planforge.llm.provider as provider_mod
from planforge.llm import ProfileConfig, get_provider, load_config


def test_load_config_loads_all_profiles(tmp_path):
    """4 프로필(interview/derive/review/plan_revise) 로드 — plan_revise 누락이 review로
    폴백하는 버그 방지 (config.example.json에는 이미 plan_revise가 있었다)."""
    cfg = tmp_path / "config.json"
    cfg.write_text('{"profiles": {"interview": {"provider": "openai", "model": "m1"}}}',
                   encoding="utf-8")
    profiles = load_config(cfg)
    assert set(profiles) == {"interview", "derive", "review", "plan_revise"}
    assert profiles["interview"].model == "m1"
    # 누락 프로필은 기본값(ollama) + 모델 미지정
    assert profiles["plan_revise"].provider == "ollama"
    assert profiles["plan_revise"].model == ""


def _tcc(name, args, index):
    return {"name": name, "args": args, "id": None, "index": index, "type": "tool_call"}


def test_base_url_env_override(monkeypatch):
    """LLM_BASE_URL 환경변수가 프로바이더 기본값을 대체한다 (컨테이너 배포용)."""
    monkeypatch.setenv("LLM_BASE_URL", "http://ollama:11434/v1")
    p = get_provider(ProfileConfig(provider="ollama", model="test-model"))
    assert p._llm.openai_api_base == "http://ollama:11434/v1"


def test_base_url_config_wins_over_env(monkeypatch):
    """config.json의 base_url이 LLM_BASE_URL 환경변수보다 우선한다."""
    monkeypatch.setenv("LLM_BASE_URL", "http://ollama:11434/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")  # openai 프로바이더는 키 존재 검사만 한다
    p = get_provider(ProfileConfig(provider="openai", model="m", base_url="http://x:1"))
    assert p._llm.openai_api_base == "http://x:1"


def test_no_auto_retry_and_timeout():
    """계약: 자동 재시도 금지(max_retries=0) + 침묵 소켓 read timeout."""
    p = get_provider(ProfileConfig(provider="ollama", model="test-model"))
    assert p._llm.max_retries == 0
    assert p._llm.request_timeout == provider_mod.REQUEST_TIMEOUT


def _provider():
    return get_provider(ProfileConfig(provider="ollama", model="test-model"))


def _chunks():
    """langchain 스트림 청크 흉내 — 텍스트/툴콜 델타가 섞인 시나리오 (기존 테스트 미러링)."""
    return [
        AIMessageChunk(content="안녕"),
        AIMessageChunk(content="하세요"),
        AIMessageChunk(content="", tool_call_chunks=[_tcc("ask_", None, 0)]),
        AIMessageChunk(content="", tool_call_chunks=[_tcc("questions", '{"questions":', 0)]),
        AIMessageChunk(content="", tool_call_chunks=[_tcc(None, '[{"text":"q1"}]}', 0)]),
        AIMessageChunk(content="", tool_call_chunks=[_tcc("update_checklist", '{"items":[]}', 1)]),
    ]


class _FakeChunkStream:
    """청크 이터레이터 — provider.stream()의 finally에서 close()를 호출한다 (7fbe594)."""

    def __init__(self, chunks):
        self._it = iter(chunks)
        self.closed = False

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._it)

    def close(self):
        self.closed = True


class _FakeBound:
    def __init__(self, chunks):
        self.chunks = chunks
        self.messages = None

    def stream(self, messages):
        self.messages = messages
        self.last_stream = _FakeChunkStream(self.chunks)
        return self.last_stream


class _FakeLLM:
    """ChatOpenAI 흉내 — bind_tools 기록 + 프리셋 청크 방출."""

    def __init__(self, chunks):
        self._chunks = chunks
        self.bound = None
        self.bind_calls = []

    def bind_tools(self, tools, tool_choice=None):
        self.bind_calls.append({"tools": tools, "tool_choice": tool_choice})
        self.bound = _FakeBound(self._chunks)
        return self.bound

    def stream(self, messages):
        """도구 없이 호출할 때의 경로 — langchain의 llm.stream(messages) 계약."""
        self.raw_messages = messages
        return _FakeChunkStream(self._chunks)


def test_stream_yields_text_and_completed_tool_calls():
    p = _provider()
    fake = _FakeLLM(_chunks())
    p._llm = fake
    tools = [{"type": "function",
              "function": {"name": "ask_questions", "parameters": {}}}]
    events = list(p.stream([{"role": "user", "content": "hi"}], tools=tools))

    # bind_tools에 tool_choice=auto로 전달됐다 (기존 SDK kwargs 동일)
    assert fake.bind_calls[0]["tool_choice"] == "auto"
    assert fake.bound.last_stream.closed  # finally에서 내부 스트림 close

    texts = [e for e in events if e["type"] == "text"]
    assert [e["delta"] for e in texts] == ["안녕", "하세요"]

    calls = [e for e in events if e["type"] == "tool_call"]
    assert len(calls) == 2
    assert calls[0]["name"] == "ask_questions"
    assert calls[0]["arguments"] == {"questions": [{"text": "q1"}]}
    assert calls[1]["name"] == "update_checklist"


def test_stream_without_tools_skips_bind():
    p = _provider()
    fake = _FakeLLM([AIMessageChunk(content="hi")])
    p._llm = fake
    assert list(p.stream([{"role": "user", "content": "hi"}])) == [
        {"type": "text", "delta": "hi"}]
    assert fake.bind_calls == []


def test_chat_stream_remains_text_only():
    """레거시 chat_stream은 텍스트만 — M1 호환 유지."""
    p = _provider()
    p._llm = _FakeLLM(_chunks())
    assert list(p.chat_stream([{"role": "user", "content": "hi"}])) == ["안녕", "하세요"]


def test_raw_string_arguments_fallback():
    """JSON 파싱 실패 arguments는 dict로 강제하지 않고 원문 문자열로 방출한다."""
    bad = '{"markdown": "no-close'
    p = _provider()
    p._llm = _FakeLLM([AIMessageChunk(content="",
                                      tool_call_chunks=[_tcc("write_plan", bad, 0)])])
    events = list(p.stream([{"role": "user", "content": "hi"}]))
    calls = [e for e in events if e["type"] == "tool_call"]
    assert calls == [{"type": "tool_call", "name": "write_plan", "arguments": bad}]


def test_messages_converted_to_langchain():
    """dict 메시지가 LangChain 메시지로 변환돼 llm에 전달된다 (tool_calls 쌍 보존)."""
    p = _provider()
    fake = _FakeLLM([AIMessageChunk(content="ok")])
    p._llm = fake
    list(p.stream([
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "call_save_facts", "type": "function",
                         "function": {"name": "save_facts",
                                      "arguments": '{"facts": []}'}}]},
        {"role": "tool", "tool_call_id": "call_save_facts", "content": "OK"},
    ]))
    msgs = fake.raw_messages
    assert isinstance(msgs[0], SystemMessage)
    assert isinstance(msgs[1], HumanMessage)
    assert isinstance(msgs[2], AIMessage)
    assert msgs[2].tool_calls == [{"name": "save_facts", "args": {"facts": []},
                                   "id": "call_save_facts", "type": "tool_call"}]
    assert isinstance(msgs[3], ToolMessage)
    assert msgs[3].tool_call_id == "call_save_facts"
    assert msgs[3].content == "OK"


def test_stream_deadline_aborts(monkeypatch):
    """STREAM_DEADLINE 초과 시 TimeoutError — 자동 재시도 없이 즉시 중단.

    Windows의 time.monotonic은 ~15.6ms 해상도라 deadline+0 직후의 실측 비교가
    불확실하므로, 시계를 주입해 두 번째 monotonic()이 반드시 앞서게 만든다.
    """
    class _FakeTime:
        def __init__(self):
            self.t = 0.0

        def monotonic(self):
            self.t += 1000.0
            return self.t

    monkeypatch.setattr(provider_mod, "time", _FakeTime())
    p = _provider()
    p._llm = _FakeLLM([AIMessageChunk(content="x")])
    with pytest.raises(TimeoutError, match="정체"):
        list(p.stream([{"role": "user", "content": "hi"}]))