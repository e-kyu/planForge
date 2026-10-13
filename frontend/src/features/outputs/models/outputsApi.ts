import { apiGet, apiPost, type Build, type Job, type Plan } from "../../../api/client";
import type { DocSlug } from "../../projects/models/docloops";

/* 산출물 API 호출 계층 (§2 Model). fetchJobs의 유일한 정의는 shared/lib/useActiveJobs에 있다. */

export const fetchBuilds = (pid: number, docSlug?: string | null) =>
  apiGet<Build[]>(
    `/api/projects/${pid}/outputs${docSlug ? `?doc_slug=${encodeURIComponent(docSlug)}` : ""}`,
  );

export const fetchPlans = (pid: number, docSlug?: string | null) =>
  apiGet<Plan[]>(
    `/api/projects/${pid}/plans${docSlug ? `?doc_slug=${encodeURIComponent(docSlug)}` : ""}`,
  );

export const enqueueDerivative = (
  pid: number,
  body: {
    kind: "slides" | "report";
    doc_slug?: DocSlug; // 문서 루프 슬러그 — doc-loop 프로젝트 생성 요청 필수(백엔드 가드 409)
    doc?: string; // plan 본문 `- 산출 문서:` 라인의 한글 유형 라벨
    fmts?: string[];
  },
) => apiPost<Job>(`/api/projects/${pid}/derivatives`, body);

/** md 산출물 미리보기 — 본문이 JSON이 아니므로 text로 읽는다. */
export async function fetchOutputText(pid: number, buildId: number): Promise<string> {
  const res = await fetch(`/api/projects/${pid}/outputs/${buildId}/download`);
  return await res.text();
}