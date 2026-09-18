# -*- coding: utf-8 -*-
"""인터뷰 에이전트 상태머신 (FR-2, plan-doc.md 이식).

한 POST = 한 턴. LLM/코드 역할 분리:
- LLM: 소스·팩트·대화 해석, 가설 초안, 질문 설계, 팩트 요약, plan.md 변환 (도구 호출로 출력)
- 코드(서버): 게이트 전이·팩트 적립·plan 검증·채번 — 도구 호출을 판정해 상태를 바꾼다

SSE: 스트리밍 토큰을 그대로 흘리고(emit), blocking 도구 호출이 카드 이벤트를
방출한 뒤 턴을 끝낸다. emit은 api/interview.py의 스레드→큐 브릿지가 소비한다.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from reportagent.plan import PlanError, filter_slides, parse_plan_text, validate_skeleton

from ..events import Event, error_event, notice_event, state_event, token_event, done_event
from ..models import (
    Fact,
    FactStatus,
    InterviewMessage,
    MessageKind,
    MessageRole,
    Plan,
    PlanOrigin,
    PlanStatus,
    SessionPhase,
    SessionStatus,
)
from ..transcript import append_message
from ..workspace import read_sources_context, write_interview_log_mirror, write_plan_mirror
from .tools import BLOCKING_TOOLS, INTERVIEW_TOOLS, ToolError, validate_tool_args

PROMPTS_DIR = Path(__file__).parent / "prompts"

MAX_TOOL_TURNS = 8   # 한 턴 내 LLM 호출 한도 (도구 루프 폭주 방지)
MAX_ROUNDS = 8       # 세션 전체 라운드 한도
PLAN_FIX_ATTEMPTS = 2  # write_plan 검증 실패 재시도 한도


class TurnError(RuntimeError):
    pass


class _EventSink(list):
    """이벤트 수집 + 즉시 방출. SSE 브릿지(emit)가 있으면 append 시점에 흘려보낸다."""

    def __init__(self, emit=None):
        super().__init__()
        self._emit = emit

    def add(self, ev: Event) -> Event:
        self.append(ev)
        if self._emit is not None:
            self._emit(ev)
        return ev


class InterviewAgent:
    """세션 1개에 바인딩된 턴 실행기. stream_fn(messages, tools)은 provider.stream 계약.

    emit(events[Event])를 주입하면 이벤트가 수집과 동시에 SSE로 흘러나간다.
    """

    def __init__(self, db: DBSession, session: InterviewSession, stream_fn,
                 sources_dirs: list[Path], settings=None, emit=None):
        self.db = db
        self.sess = session
        self.stream_fn = stream_fn
        self.sources_dirs = sources_dirs
        self.settings = settings

    # ---------------------------------------------------------------- 컨텍스트 구성 (FR-2.1)

    def _system_prompt(self) -> str:
        base = (PROMPTS_DIR / "interview.md").read_text(encoding="utf-8-sig")
        ctx = self._turn_context()
        return base + "\n\n## 이번 턴 주입 컨텍스트 (소스·확립 팩트 — 임의 추측 금지)\n\n" + ctx

    def _turn_context(self) -> str:
        parts: list[str] = []
        src = read_sources_context(self.sources_dirs)
        if src:
            parts.append("### 소스 문서\n" + src)
        facts = self.db.query(Fact).filter(
            Fact.project_id == self.sess.project_id,
            Fact.status == FactStatus.ACTIVE).all()
        if facts:
            lines = [f"- [{f.date}] {f.content} (출처: {f.source})" for f in facts]
            parts.append("### 확립 팩트 (interview-log)\n" + "\n".join(lines))
        if not parts:
            parts.append("(소스·팩트가 텅 비어 있음 — 뼈대 질문부터 시작. 임의 추측 금지)")
        return "\n\n".join(parts)

    def _history(self) -> list[dict]:
        """이력 행 → LLM 메시지. user/assistant/tool만 (event 카드는 도구 결과로 이미 반영).

        도구 호출 턴은 assistant(TOOL_CALL) 행 + tool 행 쌍으로 기록되며,
        OpenAI 프로토콜 요구대로 assistant.tool_calls → tool 결과 순서로 재구성한다.
        """
        msgs = (self.db.query(InterviewMessage)
                .filter(InterviewMessage.session_id == self.sess.id,
                        InterviewMessage.role.in_([MessageRole.USER, MessageRole.ASSISTANT,
                                                   MessageRole.TOOL]))
                .order_by(InterviewMessage.seq).all())
        out = []
        for m in msgs:
            role = m.role.value if isinstance(m.role, MessageRole) else str(m.role)
            kind = m.kind.value if isinstance(m.kind, MessageKind) else str(m.kind)
            if role == "tool":
                out.append({"role": "tool",
                            "tool_call_id": (m.payload or {}).get("tool_call_id", "t"),
                            "content": m.content})
            elif role == "assistant" and kind == "tool_call" and m.payload:
                calls = [{"id": f"call_{tc['name']}", "type": "function",
                          "function": {"name": tc["name"],
                                       "arguments": json.dumps(tc["arguments"], ensure_ascii=False)}}
                         for tc in m.payload.get("tool_calls", [])]
                out.append({"role": "assistant", "content": None, "tool_calls": calls})
            else:
                out.append({"role": role, "content": m.content})
        return out

    # ---------------------------------------------------------------- 턴 실행

    def run_turn(self, user_message: str, emit=None) -> list[Event]:
        """한 턴: LLM 스트리밍 → 도구 디스패치 → 상태 전이. 이벤트 리스트 반환.

        emit이 주어지면 이벤트가 만들어지는 즉시 흘러나간다 (SSE 실시간 스트리밍).
        """
        events = _EventSink(emit)
        self._append(MessageRole.USER, MessageKind.TEXT, content=user_message)
        messages = [{"role": "system", "content": self._system_prompt()}]
        messages += self._history()
        messages.append({"role": "user", "content": user_message})

        try:
            events.add(state_event(self.sess.phase.value, self.sess.round_no,
                                   self.sess.checklist))
            self._loop(messages, events)
        except Exception as e:  # noqa: BLE001 — 턴 실패는 세션 상태로 기록
            self.sess.phase = SessionPhase.FAILED
            self.sess.status = SessionStatus.ABORTED
            self.sess.error = f"{type(e).__name__}: {e}"
            events.add(error_event("llm_error", str(e)))
        self.db.commit()
        events.add(done_event(self.sess.phase.value, self.sess.status.value))
        return events

    def _loop(self, messages: list[dict], events: _EventSink) -> list[Event]:
        nudges = 0
        plan_fixes = 0
        for _ in range(MAX_TOOL_TURNS):
            text_parts: list[str] = []
            tool_calls: list[dict] = []
            for ev in self.stream_fn(messages, tools=INTERVIEW_TOOLS):
                if ev["type"] == "text":
                    text_parts.append(ev["delta"])
                    events.add(token_event(ev["delta"]))
                elif ev["type"] == "tool_call":
                    tool_calls.append({"name": ev["name"], "arguments": ev["arguments"]})
            text = "".join(text_parts)
            if text.strip():
                self._append(MessageRole.ASSISTANT, MessageKind.TEXT, content=text)

            # 스트리밍 폴백(D9): tool-call이 나와야 할 턴에 안 나오면 비스트리밍 1회 재시도
            if not tool_calls and not self._dispatch_from_content(events, text):
                if text.strip() and nudges == 0:
                    nudges += 1
                    messages = messages + [
                        {"role": "assistant", "content": text},
                        {"role": "user", "content":
                         "도구(ask_questions·save_facts·confirm_key_messages·update_checklist·write_plan)를 호출해 진행하라. 도구 호출 외 출력 금지."},
                    ]
                    continue
                raise TurnError("LLM이 도구 호출 없이 응답을 마쳤습니다")

            blocking = [tc for tc in tool_calls if tc["name"] in BLOCKING_TOOLS]
            non_blocking = [tc for tc in tool_calls if tc["name"] not in BLOCKING_TOOLS]
            for tc in non_blocking:
                result = self._dispatch(tc, events)
                self._persist_tool_exchange(tc, result)
                messages = messages + self._tool_messages(tc, result)
            if not blocking:
                continue  # 비차단 도구만 있으면 같은 턴에서 루프 지속
            tc = blocking[0]
            if tc["name"] == "write_plan" and plan_fixes >= PLAN_FIX_ATTEMPTS:
                raise TurnError("plan 검증 재시도 한도 초과")
            result = self._dispatch(tc, events)
            self._persist_tool_exchange(tc, result)
            messages = messages + self._tool_messages(tc, result)
            if isinstance(result, str) and result.startswith("ERROR:"):
                # 검증 실패 피드백 → 루프 지속 (재호출 유도)
                if tc["name"] == "write_plan":
                    plan_fixes += 1
                continue
            return events  # blocking 도구로 턴 종료
        raise TurnError(f"턴 내 도구 루프 한도({MAX_TOOL_TURNS}) 초과")

    def _dispatch_from_content(self, events, text: str) -> bool:
        return False  # 텍스트만으로 진행하지 않는다 — 도구 호출이 유일한 진행 경로

    def _persist_tool_exchange(self, tc: dict, result) -> None:
        """도구 교환을 이력에 영속 — 다음 턴의 _history 재구성 원료."""
        self._append(MessageRole.ASSISTANT, MessageKind.TOOL_CALL,
                     payload={"tool_calls": [{"name": tc["name"],
                                              "arguments": _as_dict(tc["arguments"])}]})
        content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        self._append(MessageRole.TOOL, MessageKind.TEXT,
                     content=content, payload={"tool_call_id": f"call_{tc['name']}"})

    def _tool_messages(self, tc: dict, result) -> list[dict]:
        """도구 실행 결과를 LLM 대화에 되돌린다."""
        content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        return [
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": f"call_{tc['name']}", "type": "function",
                             "function": {"name": tc["name"],
                                          "arguments": json.dumps(_as_dict(tc["arguments"]),
                                                                  ensure_ascii=False)}}]},
            {"role": "tool", "tool_call_id": f"call_{tc['name']}", "content": content},
        ]

    def _append(self, role: MessageRole, kind: MessageKind, content: str = "",
                payload: dict | None = None) -> None:
        append_message(self.db, self.sess.id, role, kind, content, payload)

    def _dispatch(self, tc: dict, events: _EventSink) -> str | dict:
        """도구 실행. blocking 도구 성공 시 카드+상태 이벤트 방출. 실패는 'ERROR: ...' 문자열."""
        name, args = tc["name"], tc["arguments"]
        try:
            if isinstance(args, str):
                args = json.loads(args)
            args = validate_tool_args(name, args)
        except (ToolError, json.JSONDecodeError) as e:
            return f"ERROR: {e}"

        if name == "ask_questions":
            return self._ask_questions(args, events)
        if name == "save_facts":
            return self._save_facts(args, events)
        if name == "confirm_key_messages":
            return self._confirm_key_messages(args, events)
        if name == "update_checklist":
            self.sess.checklist = args["items"]
            self._append(MessageRole.EVENT, MessageKind.STATE,
                         payload={"checklist": args["items"]})
            return {"ok": True}
        if name == "write_plan":
            return self._write_plan(args, events)
        return f"ERROR: 알 수 없는 도구 {name}"

    # ---------------------------------------------------------------- blocking 도구 구현

    def _ask_questions(self, args: dict, events: _EventSink) -> str:
        if self.sess.round_no >= MAX_ROUNDS:
            return ("ERROR: 세션 라운드 한도(8)에 도달했습니다. 부족한 항목은 (미확정)으로 명시하고 "
                    "write_plan으로 마무리하라.")
        self.sess.round_no += 1
        self.sess.pending_questions = args["questions"]
        self.sess.phase = SessionPhase.AWAITING_ANSWERS
        events.add(Event(name="questions", kind=MessageKind.QUESTIONS,
                         payload={"round": self.sess.round_no,
                                  "summary": args.get("round_summary", ""),
                                  "questions": args["questions"]}))
        self._append(MessageRole.EVENT, MessageKind.QUESTIONS,
                     payload={"round": self.sess.round_no, "questions": args["questions"]})
        events.add(state_event(self.sess.phase.value, self.sess.round_no, self.sess.checklist))
        return "OK: 질문 카드를 제시했다. 사용자 답변을 기다린다."

    def _save_facts(self, args: dict, events: _EventSink) -> str:
        # FR-2.4: 확인 전에는 팩트 저장소에 적립하지 않는다 (pending 상태)
        self.sess.pending_facts = args["facts"]
        self.sess.phase = SessionPhase.FACT_GATE
        events.add(Event(name="facts", kind=MessageKind.FACTS,
                         payload={"facts": args["facts"],
                                  "conflicts": args.get("conflicts") or []}))
        self._append(MessageRole.EVENT, MessageKind.FACTS,
                     payload={"facts": args["facts"], "conflicts": args.get("conflicts") or []})
        for c in args.get("conflicts") or []:
            events.add(notice_event(c.get("note", ""), level="warn"))
        events.add(state_event(self.sess.phase.value, self.sess.round_no, self.sess.checklist))
        return "OK: 팩트 확인 게이트를 제시했다. 사용자 승인을 기다린다."

    def _confirm_key_messages(self, args: dict, events: _EventSink) -> str:
        self.sess.pending_key_messages = args["messages"]
        self.sess.phase = SessionPhase.KEY_MESSAGE_GATE
        events.add(Event(name="key_messages", kind=MessageKind.KEY_MESSAGES,
                         payload={"messages": args["messages"]}))
        self._append(MessageRole.EVENT, MessageKind.KEY_MESSAGES,
                     payload={"messages": args["messages"]})
        events.add(state_event(self.sess.phase.value, self.sess.round_no, self.sess.checklist))
        return "OK: 핵심 메시지 승인 카드를 제시했다."

    def _write_plan(self, args: dict, events: _EventSink) -> str:
        if not self.sess.key_messages_approved:
            return "ERROR: 핵심 메시지 승인(confirm_key_messages → 사용자 승인) 전에는 plan을 작성할 수 없다."
        md = args["markdown"]
        try:
            plan = parse_plan_text(md)
            if len(plan.key_messages) != 3:
                return f"ERROR: 핵심 메시지는 정확히 3개여야 합니다 (현재 {len(plan.key_messages)}개)"
            for doc in plan.docs:
                slides = filter_slides(plan.slides, doc)
                validate_skeleton(slides)  # 원칙 8 — 미달 시 중단
        except PlanError as e:
            return f"ERROR: plan 포맷 검증 실패 — {e}"

        # DB plan 행 (SSOT) + plan.md 미러
        max_ver = self.db.query(Plan.version_no).filter(
            Plan.project_id == self.sess.project_id).order_by(Plan.version_no.desc()).first()
        version_no = (max_ver[0] if max_ver else 0) + 1
        p = Plan(project_id=self.sess.project_id, version_no=version_no, markdown=md,
                 docs=plan.docs, parsed_ok=True, status=PlanStatus.DRAFT,
                 origin=PlanOrigin.INTERVIEW)
        self.db.add(p)
        self.db.flush()
        write_plan_mirror(Path(self.sess.project.workspace_path), md)

        self.sess.phase = SessionPhase.PLAN_REVIEW
        events.add(Event(name="plan_draft", kind=MessageKind.PLAN_DRAFT,
                         payload={"plan_id": p.id, "version_no": version_no,
                                  "docs": plan.docs, "markdown": md}))
        self._append(MessageRole.EVENT, MessageKind.PLAN_DRAFT,
                     payload={"plan_id": p.id, "version_no": version_no})
        events.add(state_event(self.sess.phase.value, self.sess.round_no, self.sess.checklist))
        return f"OK: plan v{version_no}이 저장됐다. 사용자 승인을 기다린다."

    # ---------------------------------------------------------------- 팩트 커밋 (FR-2.4 — 코드 전담)

    def commit_facts(self, edits: list[dict] | None = None) -> list[dict]:
        """사용자 승인된 pending_facts를 팩트 저장소에 적립 + interview-log 미러.

        edits: [{index, content?, source?}] — 사용자가 확인 화면에서 고친 내용 반영.
        """
        pending = self.sess.pending_facts or []
        if edits:
            for e in edits:
                idx = e.get("index")
                if idx is not None and 0 <= idx < len(pending):
                    if e.get("content"):
                        pending[idx]["content"] = e["content"]
                    if e.get("source") is not None:
                        pending[idx]["source"] = e["source"]
        lines = []
        for f in pending:
            self.db.add(Fact(project_id=self.sess.project_id, session_id=self.sess.id,
                             date=date.today(), content=f["content"],
                             source=f.get("source", ""), origin="interview"))
            lines.append(f"[{date.today().isoformat()}] {f['content']} (출처: {f.get('source', '')})")
        write_interview_log_mirror(Path(self.sess.project.workspace_path), lines)
        self.sess.pending_facts = None
        self.db.commit()
        return pending


def _as_dict(args) -> dict:
    """도구 인자를 이력 재구성용 dict로 정규화 (문자열이면 파싱)."""
    if isinstance(args, str):
        try:
            return json.loads(args)
        except json.JSONDecodeError:
            return {"_raw": args}
    return args if isinstance(args, dict) else {"_raw": args}