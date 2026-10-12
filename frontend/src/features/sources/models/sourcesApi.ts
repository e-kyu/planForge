import { apiDelete, apiGet, apiUpload, type SourceFile, type UploadResult } from "../../../api/client";

/* 소스 API 호출 계층 (§2 Model). */

export const fetchProjectSources = (pid: number) =>
  apiGet<SourceFile[]>(`/api/projects/${pid}/sources`);

export const fetchGlobalSources = () => apiGet<SourceFile[]>("/api/sources");

/** POST /sources — zip은 해제 결과(saved·skipped), 단일 파일은 saved 1건·skipped 빈 배열. */
export const uploadSource = (pid: number, file: File) =>
  apiUpload<UploadResult>(`/api/projects/${pid}/sources`, file);

export const deleteSource = (pid: number, name: string) =>
  apiDelete(`/api/projects/${pid}/sources/${encodeURIComponent(name)}`);