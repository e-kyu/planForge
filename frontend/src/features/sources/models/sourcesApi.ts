import { apiDelete, apiGet, apiUpload, type SourceFile } from "../../../api/client";

/* 소스 API 호출 계층 (§2 Model). */

export const fetchProjectSources = (pid: number) =>
  apiGet<SourceFile[]>(`/api/projects/${pid}/sources`);

export const fetchGlobalSources = () => apiGet<SourceFile[]>("/api/sources");

export const uploadSource = (pid: number, file: File) =>
  apiUpload<SourceFile>(`/api/projects/${pid}/sources`, file);

export const deleteSource = (pid: number, name: string) =>
  apiDelete(`/api/projects/${pid}/sources/${encodeURIComponent(name)}`);