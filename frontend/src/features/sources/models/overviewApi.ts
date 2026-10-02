import { apiGet, apiPut, type Overview } from "../../../api/client";

/* 개요 문서 API 호출 계층 (§2 Model) — sources/overview.md는 파일이 곧 SSOT이고,
   GET은 exists 플래그로 부재를 알린다 (빈 뼈대 시작은 프론트 템플릿이 담당). */

export const fetchOverview = (pid: number) =>
  apiGet<Overview>(`/api/projects/${pid}/overview`);

export const saveOverview = (pid: number, content: string) =>
  apiPut<Overview>(`/api/projects/${pid}/overview`, { content });