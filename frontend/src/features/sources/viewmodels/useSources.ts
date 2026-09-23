import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteSource,
  fetchGlobalSources,
  fetchProjectSources,
  uploadSource,
} from "../models/sourcesApi";
import { errMsg } from "../../../shared/lib/errMsg";

/* 소스 관리 (FR-2.1) — 프로젝트 sources/(업로드·삭제) + 글로벌 sources/(읽기 전용). */

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

  const removeM = useMutation({
    mutationFn: (name: string) => deleteSource(pid, name),
    onSuccess: () => setError(null),
    onError: (e) => setError(errMsg(e)),
    onSettled: () => void refresh(),
  });

  return {
    files: ownQ.data ?? null,
    globalFiles: globalQ.data ?? null,
    error,
    upload: (fileList: FileList | null) => {
      if (!fileList || fileList.length === 0) return;
      setError(null);
      uploadM.mutate(fileList);
    },
    remove: (name: string) => {
      setError(null);
      removeM.mutate(name);
    },
    fileInput,
  };
}