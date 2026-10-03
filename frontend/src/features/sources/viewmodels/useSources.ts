import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteSource,
  fetchGlobalSources,
  fetchProjectSources,
  uploadSource,
} from "../models/sourcesApi";
import { errMsg } from "../../../shared/lib/errMsg";

/* 소스 관리 (FR-2.1) — 프로젝트 sources/(업로드·삭제) + 글로벌 sources/(읽기 전용).
 * 삭제는 확인 모달을 거친다 (useProjects의 delTarget 패턴과 동일). */

export const MAX_MB = 2;

export function useSources(pid: number) {
  const qc = useQueryClient();
  const ownQ = useQuery({ queryKey: ["sources", pid], queryFn: () => fetchProjectSources(pid) });
  const globalQ = useQuery({ queryKey: ["sources", "global"], queryFn: fetchGlobalSources });
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  async function refresh() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["sources", pid] }),
      qc.invalidateQueries({ queryKey: ["sources", "global"] }),
    ]);
  }

  const uploadM = useMutation({
    mutationFn: async (fileList: FileList) => {
      for (const f of Array.from(fileList)) {
        if (f.size > MAX_MB * 1024 * 1024) {
          throw new Error(`${f.name}: ${MAX_MB}MB 초과`);
        }
        await uploadSource(pid, f);
      }
    },
    onSuccess: async () => {
      setError(null);
      await refresh();
    },
    onError: (e) => setError(errMsg(e)),
    onSettled: () => {
      if (fileInput.current) fileInput.current.value = "";
    },
  });

  const [delTarget, setDelTarget] = useState<string | null>(null);
  const [delBusy, setDelBusy] = useState(false);
  const [delError, setDelError] = useState<string | null>(null);

  function openDelete(name: string) {
    setDelTarget(name);
    setDelError(null);
    setError(null);
  }

  function closeDelete() {
    if (delBusy) return; // 작업 중에는 닫지 않음
    setDelTarget(null);
    setDelError(null);
  }

  async function confirmDelete() {
    if (!delTarget || delBusy) return;
    setDelBusy(true);
    setDelError(null);
    try {
      await deleteSource(pid, delTarget);
      setDelTarget(null);
      await refresh();
    } catch (e) {
      setDelError(errMsg(e));
    } finally {
      setDelBusy(false);
    }
  }

  return {
    files: ownQ.data ?? null,
    globalFiles: globalQ.data ?? null,
    error,
    upload: (fileList: FileList | null) => {
      if (!fileList || fileList.length === 0) return;
      setError(null);
      uploadM.mutate(fileList);
    },
    delTarget,
    delBusy,
    delError,
    openDelete,
    closeDelete,
    confirmDelete,
    fileInput,
  };
}