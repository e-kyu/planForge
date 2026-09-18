import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  apiGet,
  apiPost,
  apiSSE,
  ApiError,
  type Message,
  type Session,
} from "../api/client";
import { Banner, Button, Empty } from "../components/ui";

/* 도구 스키마(agents/tools.py)와 대응하는 카드 데이터 형태 */
type QuestionCard = {
  text: string;
  options?: { label: string; description?: string }[];
  allow_free?: boolean;
};
type FactCard = { content: string; source?: string };

const PHASE_LABEL: Record<string, string> = {
  hypothesis: "가설/질문 대기",
  awaiting_answers: "답변 대기",
  fact_gate: "팩트 확인",
  key_message_gate: "핵심 메시지 승인",
  plan_review: "plan 검토",
  approved: "완료",
  failed: "실패",
};

/** 인터뷰 채팅 (FR-2) — SSE 턴 + 게이트 카드.
 *  POST(답변/게이트 제출)의 응답이 곧 SSE 스트림이므로(D6) 모든 진행을 run() 한 경로로 소비한다. */
export default function InterviewPanel({ pid }: { pid: number }) {
  const [session, setSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [answers, setAnswers] = useState<Record<number, { option?: number; free?: string }>>({});
  const feed = useRef<HTMLDivElement>(null);

  const sid = session?.id ?? null;

  useEffect(() => {
    // 세션 복원 — per-viewer 편의(localStorage). 서버 데이터가 권위다.
    let sidStored: number | null = null;
    try {
      sidStored = Number(localStorage.getItem(`ra-session-${pid}`)) || null;
    } catch {
      /* 저장소 접근 불가 — 무시 */
    }
    if (sidStored) {
      apiGet<Session>(`/api/interview/sessions/${sidStored}`)
        .then((s) => setSession(s))
        .catch(() => {
          try {
            localStorage.removeItem(`ra-session-${pid}`);
          } catch {
            /* 무시 */
          }
          setSession(null);
        });
    }
  }, [pid]);

  useEffect(() => {
    if (sid) void reload(sid);
  }, [sid]);

  useEffect(() => {
    feed.current?.scrollTo({ top: feed.current.scrollHeight });
  }, [messages, streaming]);

  async function reload(id: number) {
    try {
      const [s, msgs] = await Promise.all([
        apiGet<Session>(`/api/interview/sessions/${id}`),
        apiGet<Message[]>(`/api/interview/sessions/${id}/messages`),
      ]);
      setSession(s);
      setMessages(msgs);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function createSession() {
    setError(null);
    try {
      const s = await apiPost<Session>(`/api/projects/${pid}/interview/sessions`);
      try {
        localStorage.setItem(`ra-session-${pid}`, String(s.id));
      } catch {
        /* 무시 */
      }
      setSession(s);
      setMessages([]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  /** POST → SSE 소비 공용 경로. 종료(done) 후 세션·이력을 다시 당겨온다. */
  async function run(path: string, body: unknown) {
    if (!sid || busy) return;
    setBusy(true);
    setStreaming("");
    setError(null);
    try {
      await apiSSE(path, body, (ev) => {
        if (ev.name === "token") {
          setStreaming((prev) => prev + String(ev.payload.text ?? ""));
        } else if (ev.name === "error") {
          setError(String(ev.payload.message ?? ev.payload.code));
        }
        // 카드/상태 이벤트는 done 후 전체 리로드로 정리한다 (이력이 권위)
      });
      await reload(sid);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setStreaming("");
      setBusy(false);
      setAnswers({});
      setDraft("");
    }
  }

  const active = session?.status === "active";

  async function submitAnswers() {
    if (!session) return;
    const qs = session.pending_questions ?? [];
    const items: { index: number; option?: number; free_text?: string }[] = [];
    for (let i = 0; i < qs.length; i++) {
      const a = answers[i];
      if (!a) continue;
      if (a.option !== undefined) items.push({ index: i, option: a.option });
      else if (a.free?.trim()) items.push({ index: i, free_text: a.free.trim() });
    }
    if (items.length === 0) {
      setError("답변을 1개 이상 입력하세요 (모르면 '모름' 등으로 적어 주세요)");
      return;
    }
    await run(`/api/interview/sessions/${sid}/answers`, { answers: items });
  }

  if (session === null) {
    return (
      <section>
        <Empty>
          아직 인터뷰 세션이 없습니다.
          <div className="center-actions">
            <Button onClick={() => void createSession()}>인터뷰 세션 만들기</Button>
          </div>
        </Empty>
        {error && <Banner kind="error">{error}</Banner>}
      </section>
    );
  }

  const phase = session.phase;

  return (
    <section className="chat">
      <div className="chat-head">
        <span className="badge">라운드 {session.round_no}</span>
        <span className="badge">{PHASE_LABEL[phase] ?? phase}</span>
        <span className="spacer" />
        <Button variant="ghost" onClick={() => void createSession()} disabled={busy}>
          새 세션
        </Button>
      </div>
      {error && <Banner kind="error">{error}</Banner>}

      <div className="chat-feed" ref={feed}>
        {messages.map(renderMessage)}
        {streaming && (
          <div className="chat-row">
            <div className="bubble bubble-assistant streaming">{streaming}</div>
          </div>
        )}
      </div>

      <div className="chat-actions">
        {phase === "plan_review" && (
          <Banner kind="ok">
            plan.md 초안이 작성됐습니다 —{" "}
            <a href={`#/projects/${pid}/plan`}>plan 탭에서 검토·승인</a>
          </Banner>
        )}
        {phase === "approved" && (
          <Banner kind="ok">인터뷰가 완료됐습니다 — 산출물 탭에서 파생물을 생성하세요.</Banner>
        )}
        {phase === "failed" && (
          <Banner kind="error">세션 실패: {session.error ?? "원인 불명"} — 새 세션으로 다시 시도하세요.</Banner>
        )}

        {phase === "awaiting_answers" && session.pending_questions && (
          <AnswersCard
            questions={session.pending_questions as QuestionCard[]}
            answers={answers}
            onPick={(i, patch) => setAnswers((prev) => ({ ...prev, [i]: { ...prev[i], ...patch } }))}
            onSubmit={() => void submitAnswers()}
            busy={busy}
          />
        )}

        {phase === "fact_gate" && session.pending_facts && (
          <FactGate
            facts={session.pending_facts as FactCard[]}
            busy={busy}
            onConfirm={(approve, edits) =>
              void run(`/api/interview/sessions/${sid}/facts/confirm`, { approve, edits })
            }
          />
        )}

        {phase === "key_message_gate" && session.pending_key_messages && (
          <KeyGate
            items={session.pending_key_messages as string[]}
            busy={busy}
            onConfirm={(approve, feedback) =>
              void run(`/api/interview/sessions/${sid}/key-messages`, { approve, feedback })
            }
          />
        )}

        <div className="chat-input">
          <textarea
            value={draft}
            placeholder={
              phase === "hypothesis" && messages.length === 0
                ? "인터뷰를 시작하려면 아래 버튼을 누르세요"
                : "자유 텍스트로 보충·정정·잡담 (Enter 전송, Shift+Enter 줄바꿈)"
            }
            rows={2}
            disabled={busy || !active}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (draft.trim() && !busy) void run(`/api/interview/sessions/${sid}/turn`, { message: draft });
              }
            }}
          />
          {phase === "hypothesis" && messages.length === 0 ? (
            <Button onClick={() => void run(`/api/interview/sessions/${sid}/kick`, {})} disabled={busy}>
              인터뷰 시작 (가설 제시)
            </Button>
          ) : (
            <Button
              disabled={busy || !active || !draft.trim()}
              onClick={() => void run(`/api/interview/sessions/${sid}/turn`, { message: draft })}
            >
              보내기
            </Button>
          )}
        </div>
      </div>
    </section>
  );

  // --------------------------------------------------------------- 메시지 렌더

  function renderMessage(m: Message) {
    const p = (m.payload ?? {}) as Record<string, unknown>;
    switch (`${m.role}:${m.kind}`) {
      case "user:text":
        return <Bubble key={m.seq} side="right" text={m.content} />;
      case "assistant:text":
        return m.content.trim() ? <Bubble key={m.seq} side="left" text={m.content} /> : null;
      case "event:questions":
        return (
          <StaticCard key={m.seq} title={`라운드 ${p.round ?? "?"} 질문`}>
            <StaticQuestions questions={(p.questions ?? []) as QuestionCard[]} />
          </StaticCard>
        );
      case "event:facts": {
        const facts = (p.facts ?? []) as FactCard[];
        const conflicts = (p.conflicts ?? []) as { note?: string }[];
        return (
          <StaticCard key={m.seq} title="팩트 제시 (확인 대상)">
            <ul className="compact-list">
              {facts.map((f, i) => (
                <li key={i}>
                  {f.content}
                  {f.source ? <span className="hint"> — 출처: {f.source}</span> : null}
                </li>
              ))}
            </ul>
            {conflicts.length > 0 && (
              <p className="hint">⚠ 모순 감지: {conflicts.map((c) => c.note).join(" / ")}</p>
            )}
          </StaticCard>
        );
      }
      case "event:key_messages":
        return (
          <StaticCard key={m.seq} title="핵심 메시지 후보 (3개)">
            <ol className="compact-list">
              {((p.messages ?? []) as string[]).map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ol>
          </StaticCard>
        );
      case "event:plan_draft":
        return (
          <StaticCard key={m.seq} title={`plan v${p.version_no ?? "?"} 초안 작성됨`}>
            <a href={`#/projects/${pid}/plan`}>plan 탭에서 검토·승인 →</a>
          </StaticCard>
        );
      case "event:notice":
        return (
          <div key={m.seq} className="chat-row">
            <div className="bubble bubble-notice">{m.content}</div>
          </div>
        );
      case "event:error":
        return (
          <div key={m.seq} className="chat-row">
            <div className="bubble bubble-error">{m.content}</div>
          </div>
        );
      default:
        return null; // state/tool_call/tool — LLM 내부 기록은 채팅에 노출하지 않는다
    }
  }
}

function Bubble(props: { side: "left" | "right"; text: string }) {
  return (
    <div className={`chat-row chat-row-${props.side}`}>
      <div className={`bubble bubble-${props.side}`}>{props.text}</div>
    </div>
  );
}

function StaticCard(props: { title: string; children: ReactNode }) {
  return (
    <div className="chat-row">
      <div className="card chat-card">
        <div className="chat-card-title">{props.title}</div>
        {props.children}
      </div>
    </div>
  );
}

function StaticQuestions({ questions }: { questions: QuestionCard[] }) {
  return (
    <ol className="compact-list">
      {questions.map((q, i) => (
        <li key={i}>
          {q.text}
          {q.options && q.options.length > 0 && (
            <ul className="option-list">
              {q.options.map((o, j) => (
                <li key={j}>
                  {o.label}
                  {o.description ? <span className="hint"> — {o.description}</span> : null}
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ol>
  );
}

/** 답변 카드 (FR-2.3) — 선택지 클릭 + 서술형 입력. */
function AnswersCard(props: {
  questions: QuestionCard[];
  answers: Record<number, { option?: number; free?: string }>;
  onPick: (i: number, patch: { option?: number; free?: string }) => void;
  onSubmit: () => void;
  busy: boolean;
}) {
  return (
    <div className="card chat-card chat-card-active">
      <div className="chat-card-title">라운드 답변 — 선택지를 고르거나 직접 적어 주세요</div>
      <ol className="question-list">
        {props.questions.map((q, i) => (
          <li key={i}>
            <div className="q-text">{q.text}</div>
            {q.options && q.options.length > 0 && (
              <div className="options">
                {q.options.map((o, j) => (
                  <button
                    key={j}
                    className={`option ${props.answers[i]?.option === j ? "option-picked" : ""}`}
                    onClick={() => props.onPick(i, { option: j })}
                  >
                    {o.label}
                    {o.description ? <span className="hint"> — {o.description}</span> : null}
                  </button>
                ))}
              </div>
            )}
            {(q.allow_free ?? true) && (
              <input
                className="free-input"
                placeholder="직접 입력 (선택지 대신)"
                value={props.answers[i]?.free ?? ""}
                onChange={(e) => props.onPick(i, { free: e.target.value })}
              />
            )}
          </li>
        ))}
      </ol>
      <div className="center-actions">
        <Button onClick={props.onSubmit} disabled={props.busy}>
          답변 제출
        </Button>
      </div>
    </div>
  );
}

/** 팩트 확인 게이트 (FR-2.4) — 수정 가능, 승인 시에만 적립. */
function FactGate(props: {
  facts: FactCard[];
  busy: boolean;
  onConfirm: (approve: boolean, edits: { index: number; content?: string; source?: string }[]) => void;
}) {
  const [rows, setRows] = useState(props.facts.map((f) => ({ ...f })));
  const edits = rows
    .map((r, i) =>
      r.content !== props.facts[i]?.content || (r.source ?? "") !== (props.facts[i]?.source ?? "")
        ? { index: i, content: r.content, source: r.source ?? "" }
        : null,
    )
    .filter((x): x is { index: number; content: string; source: string } => x !== null);

  return (
    <div className="card chat-card chat-card-active">
      <div className="chat-card-title">팩트 확인 — 이대로 팩트 저장소에 기록할까요?</div>
      <ul className="compact-list">
        {rows.map((f, i) => (
          <li key={i}>
            <input
              className="fact-edit"
              value={f.content}
              onChange={(e) =>
                setRows((prev) => prev.map((r, j) => (j === i ? { ...r, content: e.target.value } : r)))
              }
            />
            <input
              className="fact-edit hint-input"
              placeholder="출처"
              value={f.source ?? ""}
              onChange={(e) =>
                setRows((prev) => prev.map((r, j) => (j === i ? { ...r, source: e.target.value } : r)))
              }
            />
          </li>
        ))}
      </ul>
      <div className="center-actions">
        <Button onClick={() => props.onConfirm(true, edits)} disabled={props.busy}>
          승인 · 적립
        </Button>
        <Button variant="ghost" onClick={() => props.onConfirm(false, [])} disabled={props.busy}>
          반려 (다시 제시)
        </Button>
      </div>
    </div>
  );
}

/** 핵심 메시지 승인 게이트 (FR-2.6). */
function KeyGate(props: {
  items: string[];
  busy: boolean;
  onConfirm: (approve: boolean, feedback?: string) => void;
}) {
  const [feedback, setFeedback] = useState("");
  return (
    <div className="card chat-card chat-card-active">
      <div className="chat-card-title">핵심 메시지 3개 — 승인하시겠습니까?</div>
      <ol className="compact-list">
        {props.items.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ol>
      <div className="center-actions">
        <Button onClick={() => props.onConfirm(true)} disabled={props.busy}>
          승인
        </Button>
        <Button
          variant="ghost"
          disabled={props.busy}
          onClick={() => props.onConfirm(false, feedback.trim() || undefined)}
        >
          반려
        </Button>
        <input
          className="free-input"
          placeholder="반려 사유 / 수정 방향 (선택)"
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
        />
      </div>
    </div>
  );
}