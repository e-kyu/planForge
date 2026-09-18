# -*- coding: utf-8 -*-
"""인터뷰 세션 API (FR-2).

변경 POST(kick/turn/answers/facts-confirm/key-messages)는 그 턴의 SSE 스트림을
직접 반환한다(D6). LLM 턴은 agents/interview.py 상태머신이 워커 스레드에서 실행하고,
이벤트는 큐를 통해 SSE로 흘러나온다.

동시 턴은 프로세스 내 세션 락(409)으로 직렬화한다 — 배포가 단일 uvicorn 프로세스
(docker compose)이므로 충분하다. 멀티 프로세스 전환 시 DB 기반 락으로 교체할 것.
"""
from __future__ import annotations

import queue
import threading
from collections.abc import Generator

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db, make_session_factory
from ..events import error_event
from ..errors import http_404, http_409
from ..models import (
    InterviewMessage,
    InterviewSession,
    MessageKind,
    MessageRole,
    Project,
    SessionPhase,
    SessionStatus,
)
from ..transcript import append_message
from ..workspace import workspace_path

router = APIRouter(tags=["interview"])

_STREAM_MEDIA_TYPE = "text/event-stream"


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    phase: str
    round_no: int
    status: str
    pending_questions: list | None
    pending_facts: list | None
    pending_key_messages: list | None
    checklist: list | None
    key_messages_approved: bool
    hypothesis: dict | None
    error: str | None
    created_at: object


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    role: str
    kind: str
    content: str
    payload: dict | None
    created_at: object


class SessionCreate(BaseModel):
    pass


class TurnCreate(BaseModel):
    message: str


class AnswerItem(BaseModel):
    index: int                    # pending_questions의 인덱스
    option: int | None = None     # 선택지 인덱스
    free_text: str | None = None  # 서술형/기타 답변


class AnswersCreate(BaseModel):
    answers: list[AnswerItem]


class FactsConfirmCreate(BaseModel):
    approve: bool
    edits: list[dict] | None = None  # [{index, content?, source?}] — 사용자 수정분


class KeyMessagesCreate(BaseModel):
    approve: bool
    feedback: str | None = None


def _session_or_404(db: Session, sid: int) -> InterviewSession:
    s = db.get(InterviewSession, sid)
    if s is None:
        raise http_404(f"세션 없음: {sid}")
    return s


# ---------------------------------------------------------------- 조회/생성

@router.post("/api/projects/{project_id}/interview/sessions", status_code=201,
             response_model=SessionOut)
def create_session(project_id: int, _body: SessionCreate, db: Session = Depends(get_db)):
    if db.get(Project, project_id) is None:
        raise http_404(f"프로젝트 없음: {project_id}")
    s = InterviewSession(project_id=project_id)
    db.add(s)
    db.flush()
    return SessionOut.model_validate(s)


@router.get("/api/interview/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: int, db: Session = Depends(get_db)):
    return SessionOut.model_validate(_session_or_404(db, session_id))


@router.get("/api/interview/sessions/{session_id}/messages", response_model=list[MessageOut])
def list_messages(session_id: int, after: int = 0, db: Session = Depends(get_db)):
    """트랜스크립트 + SSE 재접속 리플레이 커서 (D4/D6)."""
    _session_or_404(db, session_id)
    msgs = db.scalars(
        select(InterviewMessage)
        .where(InterviewMessage.session_id == session_id, InterviewMessage.seq > after)
        .order_by(InterviewMessage.seq)
    )
    return [MessageOut.model_validate(m) for m in msgs]


# ---------------------------------------------------------------- SSE 턴 실행 브릿지

_TURN_LOCKS: dict[int, threading.Lock] = {}
_TURN_LOCKS_GUARD = threading.Lock()

_SENTINEL = object()  # 스트림 종료 신호


def _acquire_turn_lock(session_id: int) -> threading.Lock:
    with _TURN_LOCKS_GUARD:
        lock = _TURN_LOCKS.setdefault(session_id, threading.Lock())
    if not lock.acquire(blocking=False):
        raise http_409("이 세션에서 실행 중인 턴이 있습니다 — 완료 후 다시 시도하세요")
    return lock


def _stream_turn(settings, request: Request, session_id: int, user_message: str,
                 gate_action=None) -> Response:
    """턴을 워커 스레드에서 실행하고 이벤트를 SSE로 흘려보낸다.

    gate_action(db, sess) → str | None: 턴 직전 게이트 상태 변경(팩트 커밋 등).
    반환값이 있으면 그 문자열이 synthetic user 메시지로 턴을 시작한다.
    게이트 변경과 LLM 턴은 같은 워커 스레드의 같은 DB 세션에서 실행된다 —
    요청 스레드의 세션은 스트림 동안 건드리지 않는다 (크로스 스레드 방지).
    """
    llm_overrides = request.app.state.llm_overrides

    def generate() -> Generator[str, None, None]:
        q: queue.Queue = queue.Queue()
        lock = _acquire_turn_lock(session_id)

        def work() -> None:
            db = make_session_factory(settings.database_url)()
            try:
                sess = db.get(InterviewSession, session_id)
                if sess is None:
                    q.put(error_event("session_not_found", f"세션 없음: {session_id}"))
                    return
                resume_message = gate_action(db, sess) if gate_action else None
                agent = _make_agent(db, sess, settings, llm_overrides)
                agent.run_turn(resume_message or user_message, emit=q.put)
            except Exception as e:  # noqa: BLE001 — 스트림 안에서 오류 이벤트로 보고
                q.put(error_event("turn_failed", f"{type(e).__name__}: {e}"))
            finally:
                q.put(_SENTINEL)
                db.close()

        try:
            threading.Thread(target=work, daemon=True).start()
            while True:
                ev = q.get()
                if ev is _SENTINEL:
                    break
                yield ev.sse()
        finally:
            lock.release()

    return StreamingResponse(generate(), media_type=_STREAM_MEDIA_TYPE,
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _make_agent(db, sess, settings, llm_overrides):
    from ..agents.interview import InterviewAgent
    from ..agents.llm import LLMRegistry

    registry = LLMRegistry(settings.llm_config_path, llm_overrides)
    ws = workspace_path(settings, _project_slug(db, sess.project_id))
    sources_dirs = [settings.global_sources_dir, ws / "sources"]
    return InterviewAgent(db, sess, registry.stream_fn("interview"), sources_dirs, settings)


def _project_slug(db, project_id: int) -> str:
    p = db.get(Project, project_id)
    if p is None:
        raise http_404(f"프로젝트 없음: {project_id}")
    return p.slug


# ---------------------------------------------------------------- 턴 엔드포인트

def _phase_ok(sess: InterviewSession, allowed: tuple, detail: str) -> None:
    if sess.phase not in allowed:
        raise http_409(f"{detail} (현재 phase={sess.phase.value})")


def _gate_open(sess: InterviewSession) -> None:
    if sess.phase == SessionPhase.FAILED:
        raise http_409("실패한 세션입니다 — 새 세션을 생성하세요")


def _settings(request: Request):
    return request.app.state.settings


@router.post("/api/interview/sessions/{session_id}/kick")
def kick(session_id: int, request: Request, db: Session = Depends(get_db)):
    """인터뷰 시작 (FR-2.2 가설 선제시부터)."""
    sess = _session_or_404(db, session_id)
    _phase_ok(sess, (SessionPhase.HYPOTHESIS,), "이미 시작된 인터뷰입니다")
    _gate_open(sess)
    return _stream_turn(
        _settings(request), request, session_id,
        "인터뷰를 시작한다. 주입된 소스·팩트로 가설 뼈대 초안을 먼저 제시하라. "
        "소스·팩트가 텅 비면 초안 없이 뼈대 질문부터 시작한다.")


@router.post("/api/interview/sessions/{session_id}/turn")
def turn(session_id: int, body: TurnCreate, request: Request, db: Session = Depends(get_db)):
    """자유 텍스트 턴 — 가설 확인·반박, 뼈대 정보, 게이트 화면 밖의 잡담."""
    sess = _session_or_404(db, session_id)
    if sess.status != SessionStatus.ACTIVE:
        raise http_409(f"활성 세션이 아닙니다 (status={sess.status.value})")
    _gate_open(sess)
    if not body.message.strip():
        raise http_409("빈 메시지입니다")
    return _stream_turn(_settings(request), request, session_id, body.message)


@router.post("/api/interview/sessions/{session_id}/answers")
def answers(session_id: int, body: AnswersCreate, request: Request,
            db: Session = Depends(get_db)):
    """라운드 답변 제출 (FR-2.3) — 선택지 카드 클릭이 이 엔드포인트를 호출한다."""
    sess = _session_or_404(db, session_id)
    _phase_ok(sess, (SessionPhase.AWAITING_ANSWERS,), "대기 중인 질문이 없습니다")
    _gate_open(sess)
    questions = sess.pending_questions or []
    lines = []
    for a in body.answers:
        if not 0 <= a.index < len(questions):
            raise http_409(f"질문 인덱스 범위 초과: {a.index} (0..{len(questions) - 1})")
        q = questions[a.index]
        if a.option is not None:
            opts = q.get("options") or []
            if not 0 <= a.option < len(opts):
                raise http_409(f"선택지 인덱스 범위 초과: {a.option}")
            opt = opts[a.option]
            choice = opt.get("label", "")
            if opt.get("description"):
                choice += f" — {opt['description']}"
        else:
            choice = (a.free_text or "").strip()
            if not choice:
                raise http_409(f"답변이 비어 있습니다: 질문 {a.index}")
        lines.append(f"{a.index + 1}. {q.get('text', '')}\n→ {choice}")
    message = "[라운드 답변]\n" + "\n".join(lines)
    append_message(db, session_id, MessageRole.USER, MessageKind.TEXT, content=message)
    db.commit()  # 스트림 시작 전 커밋 — 워커 스레드 세션과 (session_id, seq) 충돌 방지
    return _stream_turn(_settings(request), request, session_id, message)


@router.post("/api/interview/sessions/{session_id}/facts/confirm")
def facts_confirm(session_id: int, body: FactsConfirmCreate, request: Request,
                  db: Session = Depends(get_db)):
    """팩트 확인 게이트 (FR-2.4) — 승인 시에만 팩트 저장소에 적립된다."""
    sess = _session_or_404(db, session_id)
    _phase_ok(sess, (SessionPhase.FACT_GATE,), "대기 중인 팩트 확인이 없습니다")
    _gate_open(sess)

    def gate(dbw, sessw) -> str:
        from ..agents.interview import InterviewAgent

        agent = InterviewAgent(dbw, sessw, None, [])
        if body.approve:
            committed = agent.commit_facts(body.edits)
            return (f"[게이트] 사용자가 팩트 {len(committed)}건을 승인해 팩트 저장소에 적립했다. "
                    "체크리스트를 갱신하고 다음 진행을 계속하라.")
        sessw.pending_facts = None
        return "[게이트] 사용자가 팩트를 반려했다. 수정된 팩트를 다시 save_facts로 제시하라."

    return _stream_turn(_settings(request), request, session_id, "", gate_action=gate)


@router.post("/api/interview/sessions/{session_id}/key-messages")
def key_messages(session_id: int, body: KeyMessagesCreate, request: Request,
                 db: Session = Depends(get_db)):
    """핵심 메시지 승인 게이트 (FR-2.6)."""
    sess = _session_or_404(db, session_id)
    _phase_ok(sess, (SessionPhase.KEY_MESSAGE_GATE,), "대기 중인 핵심 메시지 승인이 없습니다")
    _gate_open(sess)

    def gate(dbw, sessw) -> str:
        if body.approve:
            sessw.key_messages_approved = True
            sessw.pending_key_messages = None
            return ("[게이트] 사용자가 핵심 메시지 3개를 승인했다. "
                    "이후 라운드는 이 3개를 성립시킬 근거 수집이 목표다.")
        sessw.pending_key_messages = None
        msg = "[게이트] 사용자가 핵심 메시지를 반려했다. 수정된 후보를 다시 confirm_key_messages로 제시하라."
        if (body.feedback or "").strip():
            msg += f" 피드백: {body.feedback.strip()}"
        return msg

    return _stream_turn(_settings(request), request, session_id, "", gate_action=gate)