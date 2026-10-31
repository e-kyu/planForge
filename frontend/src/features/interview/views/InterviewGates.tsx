import { useState } from "react";
import { Button } from "../../../shared/components/ui";
import type { AnswerDraft } from "../viewmodels/useInterview";
import type { FactCard, QuestionCard } from "./interviewTypes";

/** 답변 카드 (FR-2.3) — 선택지 클릭 + 서술형 입력. 부제에 라운드 목표(round_summary)를 표시한다.
 *  선택↔입력은 상호배타다 — 입력하면 선택이 해제, 선택하면 입력이 지워진다
 *  (과거에는 옵션 선택 중 입력값이 제출에서 조용히 폐기됐다). */
export function AnswersCard(props: {
  questions: QuestionCard[];
  answers: AnswerDraft;
  round?: number;
  summary?: string | null;
  onPick: (i: number, patch: { option?: number; free?: string }) => void;
  onSubmit: () => void;
  onSubmitAll: () => void;
  busy: boolean;
}) {
  // 추천 칩·전체제출의 공통 표시 조건 — 서술형 입력으로 반영되는 문항만 (객관 전용 문항 제외)
  const canFill = (q: QuestionCard) =>
    (q.suggestions ?? []).length > 0 && (q.allow_free ?? true);
  const hasSuggestions = props.questions.some(canFill);
  return (
    <div className="card chat-card chat-card-active">
      <div className="chat-card-title">
        {props.summary
          ? `라운드 ${props.round ?? "?"} — 목표: ${props.summary}`
          : "라운드 답변 — 선택지를 고르거나 직접 적어 주세요"}
      </div>
      <ol className="question-list">
        {props.questions.map((q, i) => (
          <li key={i}>
            <div className="q-text">{q.text}</div>
            {(q.suggestions ?? []).length > 0 && (q.allow_free ?? true) && (
              <div className="suggest-row">
                <span className="suggest-label">추천</span>
                {q.suggestions!.map((sug, k) => (
                  <button
                    key={k}
                    className="suggest-chip"
                    onClick={() => props.onPick(i, { option: undefined, free: sug })}
                  >
                    {sug}
                  </button>
                ))}
              </div>
            )}
            {q.options && q.options.length > 0 && (
              <div className="options">
                {q.options.map((o, j) => (
                  <button
                    key={j}
                    className={`option ${props.answers[i]?.option === j ? "option-picked" : ""}`}
                    onClick={() => props.onPick(i, { option: j, free: undefined })}
                  >
                    <span className="option-label">{o.label}</span>
                    {o.description ? <span className="option-desc">{o.description}</span> : null}
                  </button>
                ))}
              </div>
            )}
            {(q.allow_free ?? true) && (
              <input
                className="free-input"
                placeholder="직접 입력 (선택지 대신)"
                value={props.answers[i]?.free ?? ""}
                onChange={(e) => props.onPick(i, { option: undefined, free: e.target.value })}
              />
            )}
          </li>
        ))}
      </ol>
      <div className="center-actions">
        {hasSuggestions && (
          <Button
            variant="ghost"
            disabled={props.busy}
            title="미답변 문항을 추천 후보로 채워 제출합니다 (추천 없는 문항은 (모름)으로 전달)"
            onClick={props.onSubmitAll}
          >
            추천으로 전체 제출
          </Button>
        )}
        <Button onClick={props.onSubmit} disabled={props.busy}>
          답변 제출
        </Button>
      </div>
    </div>
  );
}

/** 팩트 확인 게이트 (FR-2.4) — 수정 가능, 승인 시에만 적립. */
export function FactGate(props: {
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
          승인 · 기록
        </Button>
        <Button variant="ghost" onClick={() => props.onConfirm(false, [])} disabled={props.busy}>
          거절 (다시 제시)
        </Button>
      </div>
    </div>
  );
}

/** 핵심 메시지 승인 게이트 (FR-2.6). */
export function KeyGate(props: {
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
          거절
        </Button>
        <input
          className="free-input"
          placeholder="거절 사유 / 수정 방향 (선택)"
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
        />
      </div>
    </div>
  );
}
