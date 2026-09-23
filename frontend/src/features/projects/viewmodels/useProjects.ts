import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Project } from "../../../api/client";
import { createProject, deleteProject, fetchProjects } from "../models/projectsApi";
import { navigate } from "../../../shared/lib/hashRoute";
import { errMsg } from "../../../shared/lib/errMsg";

/* 프로젝트 목록 + 생성·삭제 (FR-1.1) — 서버 상태는 쿼리, 액션은 뮤테이션.
 * 생성 성공 시 새 프로젝트로 이동, 삭제 성공 시 목록만 무효화한다. */

export function useProjects() {
  const qc = useQueryClient();
  const projectsQ = useQuery({ queryKey: ["projects"], queryFn: fetchProjects });

  const [notice, setNotice] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [delTarget, setDelTarget] = useState<Project | null>(null);
  const [delName, setDelName] = useState("");
  const [delBusy, setDelBusy] = useState(false);
  const [delError, setDelError] = useState<string | null>(null);

  async function create(slug: string, title: string, owner: string) {
    setBusy(true);
    setFormError(null);
    try {
      const p = await createProject({
        slug: slug.trim(),
        title: title.trim(),
        owner: owner.trim() || undefined,
      });
      navigate(`/projects/${p.id}`);
    } catch (e) {
      setFormError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  function openDelete(p: Project) {
    setDelTarget(p);
    setDelName("");
    setDelError(null);
    setNotice(null);
  }

  function closeDelete() {
    setDelTarget(null);
    setDelName("");
    setDelError(null);
  }

  async function confirmDelete() {
    if (!delTarget || delBusy) return;
    setDelBusy(true);
    setDelError(null);
    try {
      await deleteProject(delTarget.id);
      const gone = delTarget.title;
      closeDelete();
      setNotice(`삭제되었습니다: ${gone}`);
      await qc.invalidateQueries({ queryKey: ["projects"] });
    } catch (e) {
      setDelError(errMsg(e));
    } finally {
      setDelBusy(false);
    }
  }

  return {
    projects: projectsQ.data ?? null,
    error: projectsQ.isError ? errMsg(projectsQ.error) : null,
    notice,
    formError,
    setFormError,
    busy,
    create,
    delTarget,
    delName,
    setDelName,
    delBusy,
    delError,
    openDelete,
    closeDelete,
    confirmDelete,
  };
}