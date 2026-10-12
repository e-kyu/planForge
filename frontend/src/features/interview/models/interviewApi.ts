import { apiGet, apiPost, type Message, type Session } from "../../../api/client";
import type { DocSlug } from "../../projects/models/docloops";

/* 인터뷰 기능의 API 호출 계층 — client.ts 위의 얇은 래퍼 (§2 Model).
 * 턴/게이트 제출은 응답이 SSE 스트림(D6)이므로 viewmodel의 apiSSE로 직접 소비한다 — 여기엔 없다. */

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