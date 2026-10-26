import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiSSE } from "../../../api/client";
import { createSession, fetchMessages, fetchSession, turnRequest } from "../models/interviewApi";
import type { DocSlug } from "../../projects/models/docloops";
import { errMsg } from "../../../shared/lib/errMsg";

/* 인터뷰 서버 상태 + SSE 턴 머신 (§2 ViewModel).
 * POST(답변/게이트 제출)의 응답이 곧 SSE 스트림이므로(D6) 모든 진행을 run() 한 경로로 소비한다.
 * SSE 스트림은 query 캐시와 무관한 스트림 — token 버퍼는 로컬 상태로, 종료(done) 후
 * 세션·이력·팩트 쿼리를 무효화해 다시 당겨온다(이력이 권위).
 * 요청 경로·본문 조립(turnRequest)과 답변 조립(answerItems)도 여기가 소유한다 —
 * View는 typed action에 데이터만 넘긴다 (MVVM §4.3). */

/** 답변 카드의 화면 초안 — View가 소유하는 로컬 UI 상태의 형태. */
export type AnswerDraft = Record<number, { option?: number; free?: string }>;

/** 서버로 보내는 답변 1건 — AnswerItem 계약(1문항 1값). */
export type AnswerItem = { index: number; option?: number; free_text?: string };

/** pending_questions 중 답변 조립에 필요한 부분만 (도구 스키마 대응). */
type PendingQuestion = { allow_free?: boolean; suggestions?: string[] };

/** 제출할 답이 없을 때의 안내 — 빈 제출은 서버 409("전부 모름")라 클라이언트에서 막는다. */
const EMPTY_ANSWER_ERROR = "답변을 1개 이상 입력하세요 (모르면 '모름' 등으로 적어 주세요)";

/** 세션 저장 키 — 문서 루프 라우트는 문서별 분리(`pf-session-{pid}-{doc}`), 레거시는
 *  기존 키(`pf-session-{pid}`) 그대로 — 기존 사용자 세션 보존(마이그레이션 없음). */
function sessionKey(pid: number, doc: DocSlug | null): string {
  return doc ? `pf-session-${pid}-${doc}` : `pf-session-${pid}`;
}

/** 세션 복원 — per-viewer 편의(localStorage). 서버 데이터가 권위다. */
function storedSid(pid: number, doc: DocSlug | null): number | null {
  try {
    return Number(localStorage.getItem(sessionKey(pid, doc))) || null;
  } catch {
    return null; /* 저장소 접근 불가 — 무시 */
  }
}

export function useInterview(pid: number, doc: DocSlug | null = null) {
  const qc = useQueryClient();
  const [sid, setSid] = useState<number | null>(() => storedSid(pid, doc));
  const [streaming, setStreaming] = useState("");
  const [status, setStatus] = useState<string | null>(null); // 턴 내부 진행 단계 (progress 이벤트)
  const [active, setActive] = useState(false); // 이 라운드에서 토큰이 흐르는 중인지
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sessionQ = useQuery({
    queryKey: ["interview", "session", sid],
    queryFn: () => fetchSession(sid!),
    enabled: sid !== null,
    retry: false,
  });
  const messagesQ = useQuery({
    queryKey: ["interview", "messages", sid],
    queryFn: () => fetchMessages(sid!),
    enabled: sid !== null,
    retry: false,
  });

  // 복원 실패 — 저장된 sid 제거 후 "세션 없음" 상태 (원본: 복원 실패 시 storage 정리)
  useEffect(() => {
    if (sid === null || !sessionQ.isError) return;
    try {
      localStorage.removeItem(sessionKey(pid, doc));
    } catch {
      /* 무시 */
    }
    setSid(null);
  }, [sid, sessionQ.isError, pid, doc]);

  const session = sessionQ.data ?? null;
  const messages = messagesQ.data ?? [];
  const restoring = sid !== null && sessionQ.isLoading;

  function start() {
    setError(null);
    createSession(pid, doc)
      .then((s) => {
        try {
          localStorage.setItem(sessionKey(pid, doc), String(s.id));
        } catch {
          /* 무시 */
        }
        qc.setQueryData(["interview", "session", s.id], s);
        setSid(s.id);
      })
      .catch((e) => setError(errMsg(e)));
  }

  /** POST → SSE 소비 공용 경로. 종료 후 세션·이력·팩트를 무효화해 다시 당겨온다.
   *  반환값: 오류 없이 끝났는지 — true일 때만 View가 입력(답변·초안)을 비운다
   *  (오류 시 유지 — 재제출 대비). error 이벤트는 스트림 정상 종료로 도착하므로
   *  catch만으로는 잡히지 않는다 — 이벤트에서도 ok를 끈다. */
  async function run(path: string, body: unknown): Promise<boolean> {
    if (!sid || busy) return false;
    setBusy(true);
    setStreaming("");
    setStatus("context"); // optimistic — 첫 progress 이벤트 전 네트워크 왕복 구간도 커버
    setActive(false);
    setError(null);
    let ok = true; // error 이벤트·예외에서 false — false면 View가 입력을 유지한다 (재제출 대비)
    try {
      await apiSSE(path, body, (ev) => {
        if (ev.name === "token") {
          setStreaming((prev) => prev + String(ev.payload.text ?? ""));
          setActive(true);
        } else if (ev.name === "progress") {
          setStatus(String(ev.payload.step ?? ""));
          setActive(false); // 단계가 바뀌면 토큰 재대기 — 타이핑 버블로 전환
        } else if (ev.name === "error") {
          setError(String(ev.payload.message ?? ev.payload.code));
          ok = false; // error 이벤트는 스트림 정상 종료로 도착하므로 catch만으로 부족
        }
        // 카드/상태 이벤트는 done 후 쿼리 무효화로 정리한다 (이력이 권위)
      });
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["interview", "session", sid] }),
        qc.invalidateQueries({ queryKey: ["interview", "messages", sid] }),
        qc.invalidateQueries({ queryKey: ["facts", pid] }),
      ]);
      return ok;
    } catch (e) {
      setError(errMsg(e));
      return false; // 오류 시 답변·초안을 유지해 재제출하도록 한다
    } finally {
      setStreaming("");
      setStatus(null);
      setActive(false);
      setBusy(false);
    }
  }

  /** 턴/게이트 제출 — kind별 경로·본문은 model(turnRequest)이 조립한다. */
  async function submit(kind: Parameters<typeof turnRequest>[1], payload?: unknown): Promise<boolean> {
    if (!sid) return false;
    const req = turnRequest(sid, kind, payload);
    return run(req.path, req.body);
  }

  async function submitTurn(message: string): Promise<boolean> {
    return submit("turn", message);
  }

  async function submitKick(): Promise<boolean> {
    return submit("kick");
  }

  /** 답변 초안 → 제출 items 조립 (옵션 선택 우선, 없으면 비어 있지 않은 자유 입력). */
  function answerItems(draft: AnswerDraft): AnswerItem[] {
    const qs = (session?.pending_questions ?? []) as PendingQuestion[];
    const items: AnswerItem[] = [];
    for (let i = 0; i < qs.length; i++) {
      const a = draft[i];
      if (!a) continue;
      if (a.option !== undefined) items.push({ index: i, option: a.option });
      else if (a.free?.trim()) items.push({ index: i, free_text: a.free.trim() });
    }
    return items;
  }

  /** 추천 전체제출 초안 — 미답변 문항을 문항별 suggestions[0]으로 채운다 (결정론).
   *  suggestions 없는 문항은 미답변 유지 — 서버가 → (모름) 마킹으로 전달한다 (계약 문서).
   *  제출할 답이 하나도 없으면 오류를 설정하고 null을 반환한다. */
  function suggestedAnswer(draft: AnswerDraft): { next: AnswerDraft; items: AnswerItem[] } | null {
    if (!session) return null;
    const qs = (session.pending_questions ?? []) as PendingQuestion[];
    let filled = 0;
    const next: AnswerDraft = { ...draft };
    for (let i = 0; i < qs.length; i++) {
      const q = qs[i];
      const sug = q?.suggestions?.[0]; // 첫 후보 고정 — 사용자가 칩·입력으로 수정하는 여지는 유지
      // 칩 표시 조건과 동일한 채움 조건 — 서술형 입력으로 반영되는 문항만 (객관 전용 문항 미기입 → (모름))
      if (!next[i] && sug && (q.allow_free ?? true)) {
        next[i] = { option: undefined, free: sug };
        filled++;
      }
    }
    if (filled === 0 && Object.keys(draft).length === 0) {
      setError(EMPTY_ANSWER_ERROR);
      return null;
    }
    return { next, items: answerItems(next) };
  }

  async function submitAnswers(items: AnswerItem[]): Promise<boolean> {
    if (items.length === 0) {
      setError(EMPTY_ANSWER_ERROR);
      return false;
    }
    return submit("answers", items);
  }

  async function submitFactsConfirm(approve: boolean, edits: unknown[]): Promise<boolean> {
    return submit("facts-confirm", { approve, edits });
  }

  async function submitKeyMessages(approve: boolean, feedback?: string): Promise<boolean> {
    return submit("key-messages", { approve, feedback });
  }

  return {
    sid,
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
  };
}