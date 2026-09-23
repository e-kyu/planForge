import { apiGet, apiPost, type Message, type Session } from "../../../api/client";

/* 인터뷰 기능의 API 호출 계층 — client.ts 위의 얇은 래퍼 (§2 Model).
 * 턴/게이트 제출은 응답이 SSE 스트림(D6)이므로 viewmodel의 apiSSE로 직접 소비한다 — 여기엔 없다. */

export const fetchSession = (sid: number) => apiGet<Session>(`/api/interview/sessions/${sid}`);

export const fetchMessages = (sid: number) =>
  apiGet<Message[]>(`/api/interview/sessions/${sid}/messages`);

export const createSession = (pid: number) =>
  apiPost<Session>(`/api/projects/${pid}/interview/sessions`);