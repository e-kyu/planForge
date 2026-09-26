import { apiGet, apiPost, type Job, type Plan, type Review } from "../../../api/client";

/* 검수 API 호출 계층 (§2 Model). */

export const fetchReviews = (pid: number) => apiGet<Review[]>(`/api/projects/${pid}/reviews`);

export const fetchJobs = (pid: number) => apiGet<Job[]>(`/api/projects/${pid}/jobs`);

export const fetchPlans = (pid: number) => apiGet<Plan[]>(`/api/projects/${pid}/plans`);

export const enqueueReview = (pid: number) => apiPost<Job>(`/api/projects/${pid}/reviews`);

/** 선택 발견사항 plan 반영 (FR-4.3) — LLM이 고쳐 새 plan 세대(초안)를 만든다. */
export const reviseFromReview = (planId: number, reviewId: number, findingIndices: number[]) =>
  apiPost<Job>(`/api/plans/${planId}/revise-from-review`, {
    review_id: reviewId,
    finding_indices: findingIndices,
  });