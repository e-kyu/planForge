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
        """SSE 스트리밍(토큰 단위) — M2 인터뷰 채팅용. 텍스트 델타를 순서대로 내보낸다.

        스트리밍 중 tool calling 델타는 M2에서 도구 루프와 함께 확장한다."""
        kwargs = dict(model=self.model, messages=messages, stream=True)
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        stream = self._client.chat.completions.create(**kwargs)
        for event in stream:
            if event.choices and event.choices[0].delta and event.choices[0].delta.content:
                yield event.choices[0].delta.content