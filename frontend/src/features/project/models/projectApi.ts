import { apiGet, type Plan, type Project, type Review } from "../../../api/client";

/* 프로젝트 셸 관련 API (§2 Model). */

/** 탭 키 — 해시 라우트(#/projects/:id/:tab)의 tab 구간과 동일하다. */
export type ProjectTab = "interview" | "plan" | "outputs" | "review" | "sources";

export const fetchProject = (pid: number) => apiGet<Project>(`/api/projects/${pid}`);

export const fetchTabBadges = (pid: number) =>
  Promise.allSettled([
    apiGet<{ name: string }[]>(`/api/projects/${pid}/sources`),
    apiGet<{ status: string }[]>(`/api/projects/${pid}/facts`),
    apiGet<{ id: number; version_no: number }[]>(`/api/projects/${pid}/plans`),
    apiGet<{ id: number }[]>(`/api/projects/${pid}/outputs`),
    apiGet<{ red_count: number; yellow_count: number }[]>(`/api/projects/${pid}/reviews`),
  ]);

export type HeaderMetricsData = {
  plans: Plan[] | null;
  facts: { status: string }[] | null;
  reviews: Review[] | null;
};

export const fetchHeaderMetrics = (pid: number) =>
  Promise.allSettled([
    apiGet<Plan[]>(`/api/projects/${pid}/plans`),
    apiGet<{ status: string }[]>(`/api/projects/${pid}/facts`),
    apiGet<Review[]>(`/api/projects/${pid}/reviews`),
  ]);