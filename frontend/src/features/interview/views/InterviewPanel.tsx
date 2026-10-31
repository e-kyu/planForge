import { useEffect, useRef, useState } from "react";
import { Bot } from "lucide-react";
import type { DocSlug } from "../../projects/models/docloops";
import { Banner, Button, Empty } from "../../../shared/components/ui";
import { useInterview, type AnswerDraft } from "../viewmodels/useInterview";
import { FactSidePanel } from "./FactSidePanel";
import { InterviewComposer } from "./InterviewComposer";
import { InterviewFeed } from "./InterviewFeed";
import { AnswersCard, FactGate, KeyGate } from "./InterviewGates";
import type { FactCard, QuestionCard } from "./interviewTypes";
import { useStoredBoolean } from "../../../shared/lib/viewPrefs";

const PHASE_LABEL: Record<string, string> = {
  hypothesis: "가설/질문 대기",
  awaiting_answers: "답변 대기",
  fact_gate: "팩트 확인",
  key_message_gate: "핵심 메시지 승인",
  plan_review: "plan 검토",
  approved: "완료",
  failed: "실패",
};

/** 인터뷰 채팅 (FR-2) — SSE 턴 + 게이트 카드 (표현 전용 View).
 *  서버 상태·SSE 턴 머신·요청/답변 조립은 useInterview, 팩트 목록은 useFactsPanel이 보유한다
 *  (압축 카드는 FactSidePanel 소속). View는 경로·본문을 만들지 않고 typed action만 호출한다.
 *  doc: 문서 루프 슬러그(레거시 라우트는 null) — 세션 식별(localStorage 키·생성 doc_slug)만 분리된다. */
export default function InterviewPanel({ pid, doc = null }: { pid: number; doc?: DocSlug | null }) {
  const {
    session,
    messages,
    restoring,
    streaming,
    status,
    active,
    busy,
    error,
    start,
    submitTurn,
    submitKick,
    submitAnswers,
    submitFactsConfirm,
    submitKeyMessages,
    answerItems,
    suggestedAnswer,
  } = useInterview(pid, doc);
  const [draft, setDraft] = useState("");
  const [answers, setAnswers] = useState<AnswerDraft>({});
  const [factCollapsed, setFactCollapsed] = useStoredBoolean("pf-fact-side-collapsed", false);
  const feed = useRef<HTMLDivElement>(null);

  useEffect(() => {
    feed.current?.scrollTo({ top: feed.current.scrollHeight });
  }, [messages, streaming, status, active]);

  /** 턴 제출 래퍼 — 오류 없이 끝났을 때만 입력(답변·초안)을 비운다 (오류 시 유지 — 재제출 대비). */
  async function turn(action: () => Promise<boolean>) {
    const ok = await action();
    if (ok) {
      setAnswers({});
      setDraft("");
    }
  }

  /** 추천 전체제출 — 미답변 문항을 문항별 suggestions[0]으로 채워 한 번에 제출한다 (결정론).
   *  suggestions 없는 문항은 미답변 유지 — 서버가 → (모름) 마킹으로 전달한다 (계약 문서). */
  function submitAllWithSuggestions() {
    const r = suggestedAnswer(answers);
    if (!r) return;
    setAnswers(r.next); // 실패 시에도 채워진 상태가 화면에 남는다 (사용자 수정 여지)
    void turn(() => submitAnswers(r.items));
  }

  if (restoring) {
    return (
      <section>
        <Empty>인터뷰 세션 복원 중…</Empty>
      </section>
    );
  }

  if (session === null) {
    return (
      <section>
        <Empty>
          아직 인터뷰 세션이 없습니다.
          <div className="center-actions">
            <Button onClick={start}>인터뷰 세션 만들기</Button>
          </div>
        </Empty>
        {error && <Banner kind="error">{error}</Banner>}
      </section>
    );
  }

  const phase = session.phase;
  const isKick = phase === "hypothesis" && messages.length === 0;
  const canInteract = session.status === "active";

  return (
    <section className={`chat-layout ${factCollapsed ? "fact-collapsed" : ""}`}>
      <div className="chat-panel">
      <div className="chat-head">
        <span className="bot-chip" aria-hidden="true">
          <Bot />
        </span>
        <span className="badge">라운드 {session.round_no}</span>
        <span className="badge">{PHASE_LABEL[phase] ?? phase}</span>
        <span className="spacer" />
        <Button variant="ghost" onClick={start} disabled={busy}>
          새 세션
        </Button>
      </div>
      {error && <Banner kind="error">{error}</Banner>}

      <InterviewFeed
        messages={messages}
        streaming={streaming}
        active={active}
        busy={busy}
        status={status}
        phase={phase}
        pid={pid}
        feedRef={feed}
      />

      <div className="chat-actions">
        {phase === "plan_review" && (
          <Banner kind="ok">
            plan.md 초안이 작성됐습니다 —{" "}
            <a href={`#/projects/${pid}/plan`}>plan 탭에서 검토·승인</a>
          </Banner>
        )}
        {phase === "approved" && (
          <Banner kind="ok">인터뷰가 완료됐습니다 — 산출물 탭에서 산출물을 생성하세요.</Banner>
        )}
        {phase === "failed" && (
          <Banner kind="error">세션 실패: {session.error ?? "알 수 없는 오류"} — 새 세션으로 다시 시도하세요.</Banner>
        )}

        {phase === "awaiting_answers" && session.pending_questions && (
          <AnswersCard
            questions={session.pending_questions as QuestionCard[]}
            answers={answers}
            round={session.round_no}
            summary={session.pending_round_summary}
            onPick={(i, patch) => setAnswers((prev) => ({ ...prev, [i]: { ...prev[i], ...patch } }))}
            onSubmit={() => void turn(() => submitAnswers(answerItems(answers)))}
            onSubmitAll={submitAllWithSuggestions}
            busy={busy}
          />
        )}

        {phase === "fact_gate" && session.pending_facts && (
          <FactGate
            facts={session.pending_facts as FactCard[]}
            busy={busy}
            onConfirm={(approve, edits) =>
              void turn(() => submitFactsConfirm(approve, edits))
            }
          />
        )}

        {phase === "key_message_gate" && session.pending_key_messages && (
          <KeyGate
            items={session.pending_key_messages as string[]}
            busy={busy}
            onConfirm={(approve, feedback) =>
              void turn(() => submitKeyMessages(approve, feedback))
            }
          />
        )}

        <InterviewComposer
          draft={draft}
          onDraft={setDraft}
          busy={busy}
          canInteract={canInteract}
          isKick={isKick}
          onSend={() => void turn(() => submitTurn(draft))}
          onKick={() => void turn(() => submitKick())}
        />
      </div>
      </div>

      <FactSidePanel
        pid={pid}
        collapsed={factCollapsed}
        onToggle={() => setFactCollapsed(!factCollapsed)}
      />
    </section>
  );
}
