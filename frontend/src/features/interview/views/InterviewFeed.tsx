import type { ReactNode, RefObject } from "react";
import type { Message } from "../../../api/client";
import type { FactCard, QuestionCard } from "./interviewTypes";

/** progress 이벤트 step → 대기 문구 (백엔드 progress_event의 emit-only 진행 알림).
 *  llm 단계는 턴 시작 시점 세션 페이즈별로 문구를 구체화한다. */
const PROGRESS_LABEL: Record<string, string> = {
  context: "소스 문서와 팩트를 정리하는 중…",
  tool: "도구 실행 결과를 반영하는 중…",
};

const LLM_LABEL: Record<string, string> = {
  hypothesis: "가설과 질문을 준비하는 중…",
  awaiting_answers: "답변을 정리하는 중…",
  fact_gate: "팩트 기록을 준비하는 중…",
  key_message_gate: "핵심 메시지를 확정하는 중…",
};

function progressLabel(status: string, phase: string): string {
  if (status === "llm") return LLM_LABEL[phase] ?? "응답을 생성하는 중…";
  return PROGRESS_LABEL[status] ?? status;
}

/** 채팅 피드 — 이력 메시지 + 스트리밍 버블 + 진행(타이핑) 버블 (표현 전용).
 *  DOM 구조·클래스는 분할 전과 동일하게 유지한다 (e2e 선택자 보존). */
export function InterviewFeed(props: {
  messages: Message[];
  streaming: string;
  active: boolean;
  busy: boolean;
  status: string | null;
  phase: string;
  pid: number;
  feedRef: RefObject<HTMLDivElement | null>;
}) {
  return (
    <div className="chat-feed" ref={props.feedRef}>
      {props.messages.map((m) => renderMessage(m, props.pid))}
      {props.streaming && props.active && (
        <div className="chat-row">
          <div className="bubble bubble-assistant streaming">{props.streaming}</div>
        </div>
      )}
      {props.busy && props.status && !props.active && (
        <div className="chat-row">
          <div className="bubble bubble-assistant bubble-typing">
            {progressLabel(props.status, props.phase)}
            <span className="typing-dots" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------- 메시지 렌더

function renderMessage(m: Message, pid: number) {
  const p = (m.payload ?? {}) as Record<string, unknown>;
  switch (`${m.role}:${m.kind}`) {
    case "user:text":
      return <Bubble key={m.seq} side="right" text={m.content} />;
    case "assistant:text":
      return m.content.trim() ? <Bubble key={m.seq} side="left" text={m.content} /> : null;
    case "event:questions": {
      const round = typeof p.round === "number" ? p.round : null;
      const summary = typeof p.summary === "string" && p.summary ? p.summary : null;
      return (
        <StaticCard key={m.seq}
          title={summary ? `라운드 ${round ?? "?"} — 목표: ${summary}` : `라운드 ${round ?? "?"} 질문`}>
          <StaticQuestions questions={(p.questions ?? []) as QuestionCard[]} />
        </StaticCard>
      );
    }
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
        <StaticCard key={m.seq} title={`plan v${p.version_no ?? "?"} 초안이 작성됐습니다`}>
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
