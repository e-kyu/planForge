import { apiGet, apiPost, type Build, type Job, type Plan } from "../../../api/client";

/* 산출물 API 호출 계층 (§2 Model). */

export const fetchBuilds = (pid: number) => apiGet<Build[]>(`/api/projects/${pid}/outputs`);

export const fetchJobs = (pid: number) => apiGet<Job[]>(`/api/projects/${pid}/jobs`);

export const fetchPlans = (pid: number) => apiGet<Plan[]>(`/api/projects/${pid}/plans`);

export const enqueueDerivative = (
  pid: number,
  body: { kind: "slides" | "report"; doc?: string; fmts?: string[] },
) => apiPost<Job>(`/api/projects/${pid}/derivatives`, body);

/** md 산출물 미리보기 — 본문이 JSON이 아니므로 text로 읽는다. */
export async function fetchOutputText(pid: number, buildId: number): Promise<string> {
  const res = await fetch(`/api/projects/${pid}/outputs/${buildId}/download`);
  return await res.text();
}