import { apiGet, apiPost, type Plan } from "../../../api/client";

/* plan API 호출 계층 (§2 Model). */

export const fetchPlans = (pid: number) => apiGet<Plan[]>(`/api/projects/${pid}/plans`);

export const approvePlan = (planId: number) => apiPost<Plan>(`/api/plans/${planId}/approve`);

export const revisePlan = (planId: number, markdown: string) =>
  apiPost<Plan>(`/api/plans/${planId}/revise`, { markdown });