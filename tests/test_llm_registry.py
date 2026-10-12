# -*- coding: utf-8 -*-
"""LLMRegistry 단위 테스트 — 프로필 해석·오버라이드 계약 (app/shared/llm.py).

engine(planforge.llm)은 상태리스 provider만 제공하고 프로필 해석은 웹 레이어가
담당한다 — LLMRegistry가 그 유일 권위다. 오버라이드는 create_app(llm_overrides=...)
계약 경로로 앱에 도달하며, 이 테스트는 레지스트리 자체의 해석 규칙을 잠근다.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.shared.llm import LLMRegistry


class _Holder:
    """callable이 아닌 .chat/.stream 보유 오버라이드 객체 — FakeLLM류의 공통 형태."""

    def __init__(self):
        self.chat_n = 0

    def chat(self, *args, **kwargs):
        self.chat_n += 1
        return "chat"

    def stream(self, *args, **kwargs):
        return "stream"


def test_callable_override_used_directly(tmp_path):
    """callable 오버라이드는 chat_fn·stream_fn 모두 그대로 반환한다."""
    fake = lambda *a, **k: "fake"  # noqa: E731
    reg = LLMRegistry(tmp_path / "none.json", overrides={"derive": fake})
    assert reg.chat_fn("derive") is fake
    assert reg.stream_fn("derive") is fake


def test_holder_object_override_routes_chat_and_stream(tmp_path):
    """보유 객체 오버라이드 — chat은 .chat, stream은 .stream으로 분기."""
    holder = _Holder()
    reg = LLMRegistry(tmp_path / "none.json", overrides={"interview": holder})
    assert reg.chat_fn("interview") == holder.chat
    assert reg.stream_fn("interview") == holder.stream


def test_missing_config_profile_raises_keyerror(tmp_path):
    """설정 파일이 없으면 프로필 테이블이 비어 KeyError — 조용한 폴백 금지."""
    reg = LLMRegistry(tmp_path / "none.json", overrides=None)
    with pytest.raises(KeyError, match="derive"):
        reg.chat_fn("derive")
    with pytest.raises(KeyError, match="derive"):
        reg.stream_fn("derive")


def test_corrupt_config_falls_back_to_empty(tmp_path):
    """읽을 수 없는 설정은 초기화 실패로 프로필 테이블을 비운다 (조용한 폐기 —
    이후 KeyError로 노출, 오버라이드 경로는 계속 동작한다)."""
    cfg = tmp_path / "config.json"
    cfg.write_text("not json {", encoding="utf-8")
    reg = LLMRegistry(cfg, overrides=None)
    with pytest.raises(KeyError):
        reg.chat_fn("review")


def test_unoverridden_profile_uses_get_provider(monkeypatch, tmp_path):
    """오버라이드 밖 프로필은 get_provider(profiles[profile]) 경로 — 편차 10 계약."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"profiles": {
        "interview": {"provider": "openai", "model": "m1"},
        "review": {"provider": "ollama", "model": "m2"},
    }}), encoding="utf-8")
    chat = lambda *a, **k: "chat"  # noqa: E731
    stream = lambda *a, **k: "stream"  # noqa: E731
    # provider 어댑터 계약 — .stream 우선, 없으면 .chat_stream 폴백(getattr 기본값은 즉치 평가라 양쪽 필요)
    monkeypatch.setattr("app.shared.llm.get_provider",
                        lambda profile: SimpleNamespace(chat=chat, stream=stream,
                                                        chat_stream="chat_stream"))
    reg = LLMRegistry(cfg, overrides=None)
    assert reg.chat_fn("interview") is chat
    assert reg.stream_fn("review") is stream


def test_override_scoping_is_per_profile(monkeypatch, tmp_path):
    """오버라이드는 해당 프로필에만 적용 — 타 프로필은 provider 경로를 유지한다."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"profiles": {
        "derive": {"provider": "openai", "model": "m1"},
    }}), encoding="utf-8")
    holder = _Holder()
    monkeypatch.setattr("app.shared.llm.get_provider",
                        lambda profile: SimpleNamespace(chat="real-chat", stream="real-stream",
                                                        chat_stream="chat_stream"))
    reg = LLMRegistry(cfg, overrides={"interview": holder})
    assert reg.chat_fn("interview") == holder.chat     # 오버라이드 적용
    assert reg.chat_fn("derive") == "real-chat"        # 오버라이드 미적용 — provider 경로