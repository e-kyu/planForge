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
export type UploadResult = components["schemas"]["UploadResult"];
export type Overview = components["schemas"]["OverviewOut"];
export type Session = components["schemas"]["SessionOut"];
export type CompactPreview = components["schemas"]["CompactPreview"];
export type CompactApplyResult = components["schemas"]["CompactApplyResult"];
export type Message = components["schemas"]["MessageOut"];
export type DocLoop = components["schemas"]["DocLoopOut"];

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

export const apiPut = <T>(path: string, body?: unknown) =>
  api<T>(path, {
    method: "PUT",
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

/** 유휴 판정 기준 — 서버 keepalive(15s)의 4배 — 4회 소실 판정 (본수 방어). */
const SSE_IDLE_TIMEOUT_MS = 60_000;

/**
 * POST로 시작하는 SSE 스트림 소비. 답변/게이트 제출(REST POST)이 곧 스트림이 되는
 * 인터뷰 턴 계약(D6) — EventSource는 GET만 지원하므로 fetch 스트림으로 파싱한다.
 *
 * 유휴 타임아웃(기본 60초, 0 이하이면 없음): 바이트 청크가 60초 동안 오지 않으면
 * 연결을 정리하고 ApiError(504)로 재제출 가능 상태로 복귀한다 — 서버 keepalive
 * (`: ping` 코멘트 프레임)도 바이트 활동이므로 ping이 도는 한 연결은 계속 산다.
 */
export async function apiSSE(
  path: string,
  body: unknown,
  onEvent: (ev: SseEvent) => void,
  signal?: AbortSignal,
  idleTimeoutMs: number = SSE_IDLE_TIMEOUT_MS,
): Promise<void> {
  const controller = new AbortController();
  let idleAborted = false; // 유휴 타이머가 abort했는지 — 외부 취소와 구분한다
  const onExternalAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", onExternalAbort);
  }
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!res.ok || !res.body) throw new ApiError(res.status, await errorText(res));
    await parseSSE(res.body, onEvent, {
      idleTimeoutMs,
      signal: controller.signal,
      onIdle: () => {
        idleAborted = true;
        controller.abort();
      },
    });
  } catch (e) {
    // 유휴로 abort된 경우만 504로 변환 — 외부 수동 취소·fetch 단계 AbortError는 그대로 전파
    if (idleAborted && e instanceof Error && e.name === "AbortError") {
      throw new ApiError(504, "서버 응답이 지연되어 연결을 종료했습니다 — 다시 시도해 주세요");
    }
    throw e;
  } finally {
    signal?.removeEventListener("abort", onExternalAbort);
  }
}

/** 텍스트 이벤트 스트림을 `event:`/`data:` 프레임으로 분해한다.
 *  `opts.idleTimeoutMs`(0 이하·미지정이면 타임아웃 없음) 동안 바이트 청크가 오지
 *  않으면 `opts.onIdle`을 호출한다 — 파싱된 이벤트가 아닌 청크 기준이므로 코멘트
 *  프레임도 유효 활동으로 간주된다. 스트림을 직접 정리할 수 없어 만료 처리는
 *  타이머 소유 측(apiSSE — AbortController 보유)에 맡긴다. */
export async function parseSSE(
  stream: ReadableStream<Uint8Array>,
  onEvent: (ev: SseEvent) => void,
  opts?: { idleTimeoutMs?: number; signal?: AbortSignal; onIdle?: () => void },
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  const idleTimeoutMs = opts?.idleTimeoutMs ?? 0;
  let idleTimer: ReturnType<typeof setTimeout> | undefined;
  const resetIdle = () => {
    if (idleTimeoutMs <= 0) return;
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
      idleTimer = undefined;
      opts?.onIdle?.();
    }, idleTimeoutMs);
  };
  try {
    resetIdle();
    for (;;) {
      if (opts?.signal?.aborted) throw new DOMException("Aborted", "AbortError");
      const { done, value } = await reader.read();
      resetIdle(); // 바이트 청크마다 리셋 — `: ping` 코멘트 프레임도 활동이다
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
    clearTimeout(idleTimer); // 정상 종료·오류 종료 모두 타이머 정리
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