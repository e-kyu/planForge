import type { components } from "./types.gen";

/* API 계약 타입 — openapi-typescript 생성물에서 추출 (§3.1 계약 잠금) */
export type Project = components["schemas"]["ProjectOut"];
export type Job = components["schemas"]["JobOut"];
export type Fact = components["schemas"]["FactOut"];
export type Plan = components["schemas"]["PlanOut"];
export type Derivative = components["schemas"]["DerivativeOut"];
export type Build = components["schemas"]["BuildOut"];
export type Review = components["schemas"]["ReviewOut"];
export type ReviewFinding = components["schemas"]["FindingOut"];
export type SourceFile = components["schemas"]["SourceOut"];
export type Session = components["schemas"]["SessionOut"];
export type CompactPreview = components["schemas"]["CompactPreview"];
export type CompactApplyResult = components["schemas"]["CompactApplyResult"];
export type Message = components["schemas"]["MessageOut"];

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function errorText(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    return JSON.stringify(body.detail ?? body);
  } catch {
    return res.statusText;
  }
}

/** REST 래퍼 — vite proxy로 동일 오리진(/api → :8000)을 전제한다. */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) throw new ApiError(res.status, await errorText(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const apiGet = <T>(path: string) =>
  api<T>(path, { headers: { Accept: "application/json" } });

export const apiPost = <T>(path: string, body?: unknown) =>
  api<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? "{}" : JSON.stringify(body),
  });

export const apiDelete = (path: string) => api<void>(path, { method: "DELETE" });

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(path, { method: "POST", body: fd });
  if (!res.ok) throw new ApiError(res.status, await errorText(res));
  return (await res.json()) as T;
}

/* ---------------------------------------------------------------- SSE (D6) */

/** 인터뷰 SSE 이벤트 — backend/app/events.py Event(name, payload)와 대응 */
export type SseEvent = { name: string; payload: Record<string, unknown> };

/**
 * POST로 시작하는 SSE 스트림 소비. 답변/게이트 제출(REST POST)이 곧 스트림이 되는
 * 인터뷰 턴 계약(D6) — EventSource는 GET만 지원하므로 fetch 스트림으로 파싱한다.
 */
export async function apiSSE(
  path: string,
  body: unknown,
  onEvent: (ev: SseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) throw new ApiError(res.status, await errorText(res));
  await parseSSE(res.body, onEvent);
}

/** 텍스트 이벤트 스트림을 `event:`/`data:` 프레임으로 분해한다. */
export async function parseSSE(
  stream: ReadableStream<Uint8Array>,
  onEvent: (ev: SseEvent) => void,
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let sep: number;
      while ((sep = buf.indexOf("\n\n")) !== -1) {
        const frame = buf.slice(0, sep);
        buf = buf.slice(sep + 2);
        const ev = parseFrame(frame);
        if (ev) onEvent(ev);
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseFrame(frame: string): SseEvent | null {
  let name = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  try {
    return { name, payload: JSON.parse(dataLines.join("\n")) as Record<string, unknown> };
  } catch {
    return null;
  }
}