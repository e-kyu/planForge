import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiSSE } from "../../../api/client";
import { createSession, fetchMessages, fetchSession } from "../models/interviewApi";
import { errMsg } from "../../../shared/lib/errMsg";

/* 인터뷰 서버 상태 + SSE 턴 머신 (§2 ViewModel).
 * POST(답변/게이트 제출)의 응답이 곧 SSE 스트림이므로(D6) 모든 진행을 run() 한 경로로 소비한다.
 * SSE 스트림은 query 캐시와 무관한 스트림 — token 버퍼는 로컬 상태로, 종료(done) 후
 * 세션·이력·팩트 쿼리를 무효화해 다시 당겨온다(이력이 권위). */

export type InterviewTurn = { path: string; body: unknown };

/** 세션 복원 — per-viewer 편의(localStorage). 서버 데이터가 권위다. */
function storedSid(pid: number): number | null {
  try {
    return Number(localStorage.getItem(`pf-session-${pid}`)) || null;
  } catch {
    return null; /* 저장소 접근 불가 — 무시 */
  }
}

export function useInterview(pid: number) {
  const qc = useQueryClient();
  const [sid, setSid] = useState<number | null>(() => storedSid(pid));
  const [streaming, setStreaming] = useState("");
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
      localStorage.removeItem(`pf-session-${pid}`);
    } catch {
      /* 무시 */
    }
    setSid(null);
  }, [sid, sessionQ.isError, pid]);

  const session = sessionQ.data ?? null;
  const messages = messagesQ.data ?? [];
  const restoring = sid !== null && sessionQ.isLoading;

  function start() {
    setError(null);
    createSession(pid)
      .then((s) => {
        try {
          localStorage.setItem(`pf-session-${pid}`, String(s.id));
        } catch {
          /* 무시 */
        }
        qc.setQueryData(["interview", "session", s.id], s);
        setSid(s.id);
      })
      .catch((e) => setError(errMsg(e)));
  }

  /** POST → SSE 소비 공용 경로. 종료 후 세션·이력·팩트를 무효화해 다시 당겨온다.
   *  반환값: 실제로 턴이 시작됐는지 — 시작됐다면 View가 입력(답변·초안)을 비운다. */
  async function run(path: string, body: unknown): Promise<boolean> {
    if (!sid || busy) return false;
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
        // 카드/상태 이벤트는 done 후 쿼리 무효화로 정리한다 (이력이 권위)
      });
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["interview", "session", sid] }),
        qc.invalidateQueries({ queryKey: ["interview", "messages", sid] }),
        qc.invalidateQueries({ queryKey: ["facts", pid] }),
      ]);
      return true;
    } catch (e) {
      setError(errMsg(e));
      return true; // 시작은 됐음 — 입력 초기화는 원본과 동일하게 진행
    } finally {
      setStreaming("");
      setBusy(false);
    }
  }

  return {
    sid,
    session,
    messages,
    restoring,
    streaming,
    busy,
    error,
    setError,
    start,
    run,
  };
}