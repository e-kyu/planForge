# -*- coding: utf-8 -*-
"""LLM 바인딩 — 프로필 → chat_fn/stream_fn. 테스트 주입 훅: create_app(llm_overrides=...).

engine(reportagent.llm)은 상태리스 provider만 제공하므로, 웹 레이어가 프로필 해석을 담당한다.
"""
from __future__ import annotations

from typing import Callable

from reportagent.llm import ProfileConfig, get_provider, load_config

ChatFn = Callable[..., dict]
StreamFn = Callable[..., object]  # PR-3에서 Iterator[dict]로 확정


class LLMRegistry:
    def __init__(self, config_path, overrides: dict | None = None):
        self.overrides = overrides or {}
        self._profiles: dict[str, ProfileConfig] = {}
        if config_path and config_path.is_file():
            try:
                self._profiles = load_config(config_path)
            except Exception:
                self._profiles = {}

    def chat_fn(self, profile: str) -> ChatFn:
        if profile in self.overrides:
            fake = self.overrides[profile]
            return fake if callable(fake) else fake.chat
        provider = get_provider(self._profiles[profile])
        return provider.chat

    def stream_fn(self, profile: str) -> StreamFn:
        if profile in self.overrides:
            fake = self.overrides[profile]
            return getattr(fake, "stream", fake)
        provider = get_provider(self._profiles[profile])
        return getattr(provider, "stream", provider.chat_stream)