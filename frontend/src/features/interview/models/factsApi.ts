import { apiGet, apiPost, type CompactApplyResult, type CompactPreview, type Fact } from "../../../api/client";

/* 팩트 API — 인터뷰 기능(FactSidePanel·CompactCard)이 소비한다.
 * 확정 적립은 인터뷰 게이트(POST /facts/confirm → SSE)뿐이므로 여기엔 쓰기 API가 없다 (원칙 4). */

export const fetchFacts = (pid: number) => apiGet<Fact[]>(`/api/projects/${pid}/facts`);

export const fetchActiveFacts = (pid: number) =>
  apiGet<Fact[]>(`/api/projects/${pid}/facts?status=active`);

export const proposeCompact = (pid: number) => apiPost<CompactPreview>(`/api/projects/${pid}/facts/compact`);

export const applyCompact = (pid: number, groups: unknown) =>
  apiPost<CompactApplyResult>(`/api/projects/${pid}/facts/compact/apply`, { groups });