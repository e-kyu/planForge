import { apiDelete, apiGet, apiPost, type Project } from "../../../api/client";

/* 프로젝트 API 호출 계층 (§2 Model). */

export const fetchProjects = () => apiGet<Project[]>("/api/projects");

export const createProject = (body: { slug: string; title: string; owner?: string }) =>
  apiPost<Project>("/api/projects", body);

export const deleteProject = (id: number) => apiDelete(`/api/projects/${id}`);