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

/** 타입 불문 가장 최근 활성(queued/running) job — busy 배너가 가리킬 대상. */
export function latestActive(jobs: Job[]): Job | undefined {
  let latest: Job | undefined;
  for (const j of jobs) {
    const active = j.status === "queued" || j.status === "running";
    if (active && (!latest || j.id > latest.id)) latest = j;
  }
  return latest;
}

/* 실행 중 진행 상태 표시 — 백엔드 facade.report_progress가 기록한 job.progress를
 * 잡 폴링(refetchInterval 1.5s)으로 읽어 문구로 바꾼다. step 코드는 jobs facade 계약. */

type ProgressInfo = { step?: string; attempt?: number; max_attempts?: number };

/** 잡 타입별 step → 한국어 문구 (interview PROGRESS_LABEL 규약과 동일 패턴). */
const STEP_LABEL: Record<string, Record<string, string>> = {
  derive_build: { llm: "LLM 변환 중", build: "결정론 빌드 중" },
  review: { llm: "검수 분석 중" },
  plan_revise: { llm: "plan 반영 처리 중" },
};

/** running 잡의 진행 문구 — "LLM 변환 중 (재시도 2/3)" 형태. running이 아니면 null.
 * progress가 아직 기록되지 않은 단계(예: review의 결정론 대조 구간)는 fallback 사용. */
export function progressText(j: Job, fallback = "처리 중"): string | null {
  if (j.status !== "running") return null;
  const p = j.progress as ProgressInfo | null | undefined;
  const label = p ? (STEP_LABEL[j.type]?.[p.step ?? ""] ?? fallback) : fallback;
  const retry =
    p?.attempt && p.attempt > 1
      ? ` (재시도 ${p.attempt}/${p.max_attempts ?? "-"})`
      : "";
  return label + retry;
}

/** started_at 기반 경과 문구 — "경과 2분 13초". running이 아니거나 시작 전이면 null.
 * 갱신은 잡 폴링 주기에 의존한다 (활성 중 1.5초 refetchInterval이 리렌더를 유발). */
export function elapsedText(j: Job, now: number): string | null {
  if (j.status !== "running" || !j.started_at) return null;
  const s = Math.max(0, Math.floor((now - new Date(j.started_at).getTime()) / 1000));
  if (s < 60) return `경과 ${s}초`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (m < 60) return `경과 ${m}분 ${r}초`;
  return `경과 ${Math.floor(m / 60)}시간 ${String(m % 60).padStart(2, "0")}분`;
}