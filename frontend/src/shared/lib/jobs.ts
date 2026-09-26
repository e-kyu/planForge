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