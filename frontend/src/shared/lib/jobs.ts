import type { Job } from "../../api/client";

/* job 목록 파생 셀렉터 — review·outputs feature 공용. 배너는 "이력"이 아니라
 * "마지막 상태"를 반영해야 하므로 타입별 최신 job 기준으로 판별한다.
 * (실패 job은 DB 이력에 영구 남으므로 이력 기반 필터는 배너가 영구 잔존하게 만든다.) */

/** 타입별 최신 job — id 자동증가이므로 최대 id가 최신 (list_jobs가 id 오름차순 반환). */
export function latestByType(jobs: Job[], type: string): Job | undefined {
  let latest: Job | undefined;
  for (const j of jobs) if (j.type === type && (!latest || j.id > latest.id)) latest = j;
  return latest;
}

/** 타입별 최신 job 중 실패인 것 — 해당 타입의 최신 job이 성공이면 과거 실패는 숨긴다. */
export function latestFailed(jobs: Job[]): Job[] {
  const byType = new Map<string, Job>();
  for (const j of jobs) {
    const cur = byType.get(j.type);
    if (!cur || j.id > cur.id) byType.set(j.type, j);
  }
  return [...byType.values()].filter((j) => j.status === "failed");
}

/** 타입 불문 현재 활성(queued/running) job — busy 배너·pill이 가리킬 대상.
 * running을 queued보다 우선한다: 직렬 워커 하에서 큐가 밀리면 최신 id 잡은 queued일
 * 수밖에 없어 "마지막 클릭 잡" 기준이면 실제 실행 중 잡의 진행(변환/빌드·경과)이
 * 헤드라인에서 숨겨진다. running이 없을 때만 최신 queued를 가리킨다. */
export function latestActive(jobs: Job[]): Job | undefined {
  let running: Job | undefined;
  let latest: Job | undefined;
  for (const j of jobs) {
    if (j.status === "running" && (!running || j.id > running.id)) running = j;
    if ((j.status === "queued" || j.status === "running") && (!latest || j.id > latest.id))
      latest = j;
  }
  return running ?? latest;
}

/** 활성(queued/running) 잡 존재 확인 — 폴링 주기·busy 배너의 공용 조건. */
export function hasActive(jobs: Job[] | undefined): boolean {
  return Boolean(jobs?.some((j) => j.status === "queued" || j.status === "running"));
}

export const JOB_TYPE_LABEL: Record<string, string> = {
  derive_build: "파생물 생성",
  review: "검수",
  plan_revise: "plan 반영",
};

/* 실행 중 진행 상태 표시 — 백엔드 facade.report_progress가 기록한 job.progress를
 * 잡 폴링(refetchInterval 1.5s)으로 읽어 문구로 바꾼다. step 코드는 jobs facade 계약. */

type ProgressInfo = { step?: string; attempt?: number; max_attempts?: number; detail?: string };

/** 잡 타입별 step → 한국어 문구 (interview PROGRESS_LABEL 규약과 동일 패턴). */
const STEP_LABEL: Record<string, Record<string, string>> = {
  derive_build: { llm: "LLM 변환 중", build: "결정론 빌드 중" },
  review: { llm: "검수 분석 중" },
  plan_revise: { llm: "plan 반영 처리 중" },
};

/** running 잡의 진행 문구 — "결정론 빌드 중 — HTML 작성 중 (재시도 2/3)" 형태. running이 아니면 null.
 * progress가 아직 기록되지 않은 단계(예: review의 결정론 대조 구간)는 fallback 사용. */
export function progressText(j: Job, fallback = "처리 중"): string | null {
  if (j.status !== "running") return null;
  const p = j.progress as ProgressInfo | null | undefined;
  const label = p ? (STEP_LABEL[j.type]?.[p.step ?? ""] ?? fallback) : fallback;
  const detail = p?.detail ? ` — ${p.detail}` : "";
  const retry =
    p?.attempt && p.attempt > 1
      ? ` (재시도 ${p.attempt}/${p.max_attempts ?? "-"})`
      : "";
  return label + detail + retry;
}

/** started_at 기반 경과 문구 — "경과 2분 13초". running이 아니거나 시작 전이면 null.
 * 폴링 결과가 동일하면 structural sharing으로 리렌더가 없어 경과가 멈춘다 — 갱신은
 * 각 화면이 useTickingNow 틱으로 지금 시각을 흘려보내야 한다 (now 인자). */
export function elapsedText(j: Job, now: number): string | null {
  if (j.status !== "running" || !j.started_at) return null;
  const s = Math.max(0, Math.floor((now - new Date(j.started_at).getTime()) / 1000));
  if (s < 60) return `경과 ${s}초`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (m < 60) return `경과 ${m}분 ${r}초`;
  return `경과 ${Math.floor(m / 60)}시간 ${String(m % 60).padStart(2, "0")}분`;
}

/** running 잡의 배너/pill 공용 문구 — "파생물 생성 — LLM 변환 중 · 경과 12초".
 * queued 짝(queuedStateText)과 달리 running 전용 — status가 아니면 null. */
export function jobStateText(j: Job, now: number, fallback = "처리 중"): string | null {
  if (j.status !== "running") return null;
  const progress = progressText(j, fallback);
  if (progress === null) return null;
  const elapsed = elapsedText(j, now);
  return `${JOB_TYPE_LABEL[j.type] ?? j.type} — ${progress}${elapsed ? ` · ${elapsed}` : ""}`;
}

/** queued 잡의 짧은 대기 문구 — pill용. 배너(Outputs)는 긴 안내를 갖고 있어 그쪽은 직접 사용. */
export function queuedStateText(j: Job): string {
  return `${JOB_TYPE_LABEL[j.type] ?? j.type} — 작업 대기 중`;
}