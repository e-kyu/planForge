# -*- coding: utf-8 -*-
"""LLM provider 추상화 계층 — langchain-openai ChatOpenAI 어댑터.

계약 (§3.1 — docs/architecture-decisions.md 편차 10으로 의도적 변경):
- OpenAI 호환 단일 프로토콜 — ollama·openai를 base_url/키 차이만으로 소화.
  트랜스포트는 langchain-openai ChatOpenAI (하위 SDK는 openai).
- anthropic SDK 사용 금지. 프로바이더 추가 가능한 인터페이스.
- 모델은 설정 파일의 단계별 프로필(interview/derive/review)로 지정 — 기본값 미지정(운영자가 확정).
- API 키는 서버 환경변수로만 관리 (브라우저 노출 금지).

호출 사이트 계약은 불변: chat_fn = chat(messages, tools) -> {"content", "tool_calls"},
stream_fn = stream(messages, tools) -> Iterator[{"type": "text"|"tool_call", ...}].
dict↔LangChain 메시지 변환은 이 모듈 내부에만 존재한다.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

PROFILES = ("interview", "derive", "review", "plan_revise")
DEFAULT_BASE_URLS = {
    "ollama": "http://localhost:11434/v1",
    "openai": "https://api.openai.com/v1",
}
REQUEST_TIMEOUT = 600.0  # 초 — 침묵 소켓에 무한 대기하지 않는다 (사고: derive 호출 정체)
STREAM_DEADLINE = 900.0  # 초 — 호출 1건의 총 벽시계 한도. keepalive 트리클은 read timeout이
# 못 잡는다 (사고 2건: ollama cloud 스트림이 유효 출력 없이 12분+ 정체). 초과 시 호출을
# 중단하고 TimeoutError — 잡은 failed로 기록되고 사용자가 재실행한다 (자동 재시도 금지).


@dataclass
class ProfileConfig:
    """단계별 LLM 프로필 (설정 파일의 profiles.<단계>)."""
    provider: str            # "ollama" | "openai"
    model: str               # 미지정 금지 — 배포 시점 확정
    base_url: str = ""       # 빈 값이면 프로바이더 기본값
    api_key_env: str = "OPENAI_API_KEY"


def load_config(path: str | Path) -> dict:
    """설정 파일 로드: {"profiles": {interview|derive|review|plan_revise: {...}}}.
    누락 프로필은 기본값(ollama)+모델 미지정."""
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


def _resolve_base_url(profile: ProfileConfig) -> str:
    """우선순위: config.json의 base_url > LLM_BASE_URL 환경변수 > 프로바이더 기본값.
    컨테이너 배포에서 ollama가 localhost가 아니므로 환경변수로 기본값을 대체한다."""
    return (
        profile.base_url
        or os.environ.get("LLM_BASE_URL", "")
        or DEFAULT_BASE_URLS.get(profile.provider)
    )


def _resolve_api_key(profile: ProfileConfig) -> str:
    if profile.provider == "openai":
        api_key = os.environ.get(profile.api_key_env, "")
        if not api_key:
            raise ValueError(f"환경변수 {profile.api_key_env}에 API 키가 없습니다")
        return api_key
    return "ollama"  # 사내 서버 내부 통신 — 더미 키


class OpenAICompatProvider:
    """langchain-openai ChatOpenAI 기반 OpenAI 호환 provider (ollama/openai 공용)."""

    def __init__(self, profile: ProfileConfig):
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise SystemExit("langchain-openai가 필요합니다: pip install langchain-openai")
        if not profile.model:
            raise ValueError("모델이 설정되지 않았습니다 (config의 profiles.<단계>.model 지정 필수)")
        self.model = profile.model
        # max_retries=0 필수 — 계약상 자동 재시도 금지 (failed로 기록, 사용자가 재실행)
        self._llm = ChatOpenAI(
            model=profile.model,
            base_url=_resolve_base_url(profile),
            api_key=_resolve_api_key(profile),
            timeout=REQUEST_TIMEOUT,
            max_retries=0,
        )

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """1회 완료 호출. tool calling 지원. 반환: {"content": str|None, "tool_calls": [{name, arguments}]}

        비스트리밍 응답은 생성이 길어질 때 첫 바이트까지 침묵해 ReadTimeout이 난다
        (사고: ollama cloud glm-5.3 derive 호출). 그래서 내부적으로 스트리밍으로
        받아 누적한다 — 인터페이스(chat_fn 계약)는 그대로 유지된다.
        """
        content_parts: list[str] = []
        tool_calls: list[dict] = []
        for ev in self.stream(messages, tools):
            if ev["type"] == "text":
                content_parts.append(ev["delta"])
            else:  # tool_call
                tool_calls.append({"name": ev["name"], "arguments": ev["arguments"]})
        return {"content": "".join(content_parts) or None, "tool_calls": tool_calls}

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
        lc_msgs = _to_lc_messages(messages)
        llm = self._llm.bind_tools(tools, tool_choice="auto") if tools else self._llm
        t_start = time.monotonic()
        deadline = t_start + STREAM_DEADLINE
        pending: dict[int, dict] = {}  # tool_call index → {name, arguments}
        inner = llm.stream(lc_msgs)
        first_token_at: float | None = None  # 유효 델타(텍스트/툴콜 인자) 1차 도착 시각

        def _mark_first_token() -> None:
            nonlocal first_token_at
            if first_token_at is None:
                first_token_at = time.monotonic()
                ttfb = first_token_at - t_start
                if ttfb > 30.0:
                    print(f"[llm] {self.model} 첫 토큰 지연 {ttfb:.0f}s — 생성 전 정체",
                          flush=True)

        try:
            for chunk in inner:
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"LLM 호출이 {STREAM_DEADLINE:.0f}초를 넘었다 — 스트림이 정체됐다 "
                        "(keepalive 트리클은 read timeout으로 잡히지 않는다)")
                for part in _text_deltas(chunk):
                    _mark_first_token()
                    yield {"type": "text", "delta": part}
                for tc in chunk.tool_call_chunks or []:
                    idx = tc.get("index")
                    if idx is None:
                        idx = 0
                    slot = pending.setdefault(idx, {"name": "", "arguments": ""})
                    if tc.get("name"):
                        slot["name"] += tc["name"]
                    if tc.get("args"):
                        slot["arguments"] += tc["args"]
                        _mark_first_token()
        finally:
            inner.close()  # 정체 연결을 즉시 닫는다 — 프로세스가 소켓을 붙잡지 않게
        if first_token_at is not None:
            print(f"[llm] {self.model} 스트림 완료 "
                  f"(총 {time.monotonic() - t_start:.0f}s, "
                  f"첫 토큰까지 {first_token_at - t_start:.0f}s)", flush=True)
        else:
            print(f"[llm] {self.model} 스트림 종료 — 유효 출력 없음 "
                  f"({time.monotonic() - t_start:.0f}s)", flush=True)
        # 스트림 종료 후 완성된 도구 호출을 순서대로 방출
        for idx in sorted(pending):
            slot = pending[idx]
            try:
                args = json.loads(slot["arguments"]) if slot["arguments"] else {}
            except json.JSONDecodeError:
                args = slot["arguments"]
            yield {"type": "tool_call", "name": slot["name"], "arguments": args}


def _text_deltas(chunk) -> list[str]:
    """AIMessageChunk → 텍스트 델타 문자열 목록. content는 str 또는 content-block 리스트."""
    content = chunk.content
    if isinstance(content, str):
        return [content] if content else []
    if isinstance(content, list):
        return [blk.get("text", "") for blk in content
                if isinstance(blk, dict) and blk.get("text")]
    return []


def _as_args_dict(raw) -> dict:
    """도구 호출 arguments(OpenAI 프로토콜상 JSON 문자열) → dict. 파싱 실패 시 원문 보존."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw": raw}
        return parsed if isinstance(parsed, dict) else {"_raw": raw}
    return {}


def _to_ai_message(content, tool_calls: list[dict]):
    from langchain_core.messages import AIMessage
    calls = []
    for tc in tool_calls:
        fn = tc.get("function") or {}
        name = fn.get("name") or tc.get("name") or ""
        calls.append({"name": name,
                      "args": _as_args_dict(fn.get("arguments", tc.get("arguments"))),
                      "id": tc.get("id") or f"call_{name}",
                      "type": "tool_call"})
    if calls:
        return AIMessage(content=content or "", tool_calls=calls)
    return AIMessage(content=content or "")


def _to_lc_messages(messages: list[dict]) -> list:
    """OpenAI 프로토콜 dict → LangChain 메시지. 히스토리 재구성은 dict 기반이므로
    (tests/fakes.py의 dict 어설션, DB interview_messages) 변환은 provider 내부에만 둔다."""
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

    out: list = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if role == "system":
            out.append(SystemMessage(content=content or ""))
        elif role == "user":
            out.append(HumanMessage(content=content or ""))
        elif role == "assistant":
            out.append(_to_ai_message(content, m.get("tool_calls") or []))
        elif role == "tool":
            out.append(ToolMessage(content=content if content is not None else "",
                                   tool_call_id=m.get("tool_call_id", "t")))
        else:
            raise ValueError(f"알 수 없는 메시지 role: {role}")
    return out