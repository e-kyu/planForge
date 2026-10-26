import { apiGet, apiPost, type Message, type Session } from "../../../api/client";
import type { DocSlug } from "../../projects/models/docloops";

/* 인터뷰 기능의 API 호출 계층 — client.ts 위의 얇은 래퍼 (§2 Model).
 * 턴/게이트 제출은 응답이 SSE 스트림(D6)이므로 viewmodel의 apiSSE로 직접 소비한다 — 여기엔 없다.
 * 다만 경로·본문 조립은 View가 아니라 이 계층이 소유한다 (MVVM §4.3 — View는 데이터만 전달). */

export type InterviewTurnRequest = { path: string; body: unknown };

/** 턴/게이트 제출 요청 조립 — 실제 POST·SSE 소비는 useInterview의 run이 담당한다.
 *  kind별 경로·본문 계약: turn `{message}`, kick `{}`, answers `{answers}`,
 *  facts-confirm `{approve, edits}`, key-messages `{approve, feedback}`. */
export function turnRequest(
  sid: number,
  kind: "turn" | "kick" | "answers" | "facts-confirm" | "key-messages",
  payload?: unknown,
): InterviewTurnRequest {
  const base = `/api/interview/sessions/${sid}`;
  switch (kind) {
    case "turn":
      return { path: `${base}/turn`, body: { message: String(payload ?? "") } };
    case "kick":
      return { path: `${base}/kick`, body: {} };
    case "answers":
      return { path: `${base}/answers`, body: { answers: payload ?? [] } };
    case "facts-confirm": {
      const p = (payload ?? {}) as { approve?: boolean; edits?: unknown[] };
      return {
        path: `${base}/facts/confirm`,
        body: { approve: p.approve ?? false, edits: p.edits ?? [] },
      };
    }
    case "key-messages": {
      const p = (payload ?? {}) as { approve?: boolean; feedback?: string };
      return {
        path: `${base}/key-messages`,
        // feedback undefined는 JSON.stringify가 생략한다 (기존 본문과 동일).
        body: { approve: p.approve ?? false, feedback: p.feedback },
      };
    }
  }
}

export const fetchSession = (sid: number) => apiGet<Session>(`/api/interview/sessions/${sid}`);

export const fetchMessages = (sid: number) =>
  apiGet<Message[]>(`/api/interview/sessions/${sid}/messages`);

/** 세션 생성 — doc_slug가 있으면 문서 루프 세션(백엔드 require_session_doc 게이트).
 *  레거시( doc_slug 미전달)는 기존 와이어 포맷("{}") 그대로 유지한다. */
export const createSession = (pid: number, docSlug?: DocSlug | null) =>
  apiPost<Session>(
    `/api/projects/${pid}/interview/sessions`,
    docSlug ? { doc_slug: docSlug } : undefined,
  );