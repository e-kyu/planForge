# -*- coding: utf-8 -*-
"""LLM provider 추상화 계층.

계약 (AGENT-DEV-REQUEST.md §3.1):
- openai SDK 기반 OpenAI 호환 단일 프로토콜 — ollama·openai를 base_url/키 차이만으로 소화.
- anthropic SDK 사용 금지. 프로바이더 추가 가능한 인터페이스.
- 모델은 설정 파일의 단계별 프로필(interview/derive/review)로 지정 — 기본값 미지정(운영자가 확정).
- API 키는 서버 환경변수로만 관리 (브라우저 노출 금지).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

PROFILES = ("interview", "derive", "review")
DEFAULT_BASE_URLS = {
    "ollama": "http://localhost:11434/v1",
    "openai": "https://api.openai.com/v1",
}


@dataclass
class ProfileConfig:
    """단계별 LLM 프로필 (설정 파일의 profiles.<단계>)."""
    provider: str            # "ollama" | "openai"
    model: str               # 미지정 금지 — 배포 시점 확정
    base_url: str = ""       # 빈 값이면 프로바이더 기본값
    api_key_env: str = "OPENAI_API_KEY"


def load_config(path: str | Path) -> dict:
    """설정 파일 로드: {"profiles": {interview|derive|review: {...}}}. 누락 프로필은 기본값(ollama)+모델 미지정."""
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    profiles = {}
    for name in PROFILES:
        p = raw.get("profiles", {}).get(name, {})
        profiles[name] = ProfileConfig(
            provider=p.get("provider", "ollama"),
            model=p.get("model", ""),
            base_url=p.get("base_url", ""),
            api_key_env=p.get("api_key_env", "OPENAI_API_KEY"),
        )
    return profiles


def get_provider(profile: ProfileConfig):
    """프로필 → OpenAI 호환 클라이언트. provider 확장 지점 (새 프로바이더는 여기에 추가)."""
    return OpenAICompatProvider(profile)


class OpenAICompatProvider:
    """openai SDK 기반 OpenAI 호환 provider (ollama/openai 공용)."""

    def __init__(self, profile: ProfileConfig):
        try:
            from openai import OpenAI
        except ImportError:
            raise SystemExit("openai SDK가 필요합니다: pip install openai")
        if not profile.model:
            raise ValueError("모델이 설정되지 않았습니다 (config의 profiles.<단계>.model 지정 필수)")
        base_url = profile.base_url or DEFAULT_BASE_URLS.get(profile.provider)
        if profile.provider == "openai":
            api_key = os.environ.get(profile.api_key_env, "")
            if not api_key:
                raise ValueError(f"환경변수 {profile.api_key_env}에 API 키가 없습니다")
        else:
            api_key = "ollama"  # 사내 서버 내부 통신 — 더미 키
        self.model = profile.model
        self._client = OpenAI(base_url=base_url, api_key=api_key)

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """1회 완료 호출. tool calling 지원. 반환: {"content": str|None, "tool_calls": [{name, arguments}]}"""
        kwargs = dict(model=self.model, messages=messages)
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        resp = self._client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        tool_calls = []
        for tc in (msg.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = tc.function.arguments
            tool_calls.append({"name": tc.function.name, "arguments": args})
        return {"content": msg.content, "tool_calls": tool_calls}

    def chat_stream(self, messages: list[dict], tools: list[dict] | None = None) -> Iterator[str]:
        """SSE 스트리밍(토큰 단위) — 레거시 텍스트 스트림. 새 코드는 stream()을 사용한다."""
        for ev in self.stream(messages, tools):
            if ev["type"] == "text":
                yield ev["delta"]

    def stream(self, messages: list[dict], tools: list[dict] | None = None) -> Iterator[dict]:
        """SSE 스트리밍 + tool calling 델타 누적 (M2 인터뷰 도구 루프용).

        반환 이벤트: {"type": "text", "delta": str}
                     {"type": "tool_call", "name": str, "arguments": dict-or-str}  (인덱스별 완성 시 1회)
        """
        kwargs = dict(model=self.model, messages=messages, stream=True)
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        stream = self._client.chat.completions.create(**kwargs)
        pending: dict[int, dict] = {}  # tool_call index → {name, arguments}
        for event in stream:
            if not event.choices:
                continue
            delta = event.choices[0].delta
            if delta is None:
                continue
            if delta.content:
                yield {"type": "text", "delta": delta.content}
            for tc in (delta.tool_calls or []):
                slot = pending.setdefault(tc.index, {"name": "", "arguments": ""})
                if tc.function and tc.function.name:
                    slot["name"] += tc.function.name
                if tc.function and tc.function.arguments:
                    slot["arguments"] += tc.function.arguments
        # 스트림 종료 후 완성된 도구 호출을 순서대로 방출
        for idx in sorted(pending):
            slot = pending[idx]
            try:
                args = json.loads(slot["arguments"]) if slot["arguments"] else {}
            except json.JSONDecodeError:
                args = slot["arguments"]
            yield {"type": "tool_call", "name": slot["name"], "arguments": args}