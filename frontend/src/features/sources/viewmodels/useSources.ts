import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteSource,
  fetchGlobalSources,
  fetchProjectSources,
  uploadSource,
} from "../models/sourcesApi";
import { errMsg } from "../../../shared/lib/errMsg";
import { MAX_SOURCE_MB, MAX_ZIP_MB } from "../../../shared/lib/uploadLimits";

/* 소스 관리 (FR-2.1) — 프로젝트 sources/(업로드·삭제) + 글로벌 sources/(읽기 전용).
 * 삭제는 확인 모달을 거친다 (useProjects의 delTarget 패턴과 동일).
 * 업로드 상한은 shared/lib/uploadLimits — zip 컨테이너는 별도 상한(MAX_ZIP_MB),
 * 단건 텍스트 파일은 MAX_SOURCE_MB를 적용한다. */

/** 업로드 결과 보고 — UploadResult(saved·skipped)를 파일 갯수만큼 누적해 뷰에 노출한다. */
export type UploadReport = {
  savedCount: number;
  skipped: { name: string; reason: string }[];
};

export function useSources(pid: number) {
  const qc = useQueryClient();
  const ownQ = useQuery({ queryKey: ["sources", pid], queryFn: () => fetchProjectSources(pid) });
  const globalQ = useQuery({ queryKey: ["sources", "global"], queryFn: fetchGlobalSources });
  const [error, setError] = useState<string | null>(null);
  const [uploadReport, setUploadReport] = useState<UploadReport | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  async function refresh() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["sources", pid] }),
      qc.invalidateQueries({ queryKey: ["sources", "global"] }),
    ]);
  }

  const uploadM = useMutation({
    mutationFn: async (fileList: FileList) => {
      let savedCount = 0;
      let skipped: UploadReport["skipped"] = [];
      for (const f of Array.from(fileList)) {
        const mb = f.name.toLowerCase().endsWith(".zip") ? MAX_ZIP_MB : MAX_SOURCE_MB;
        if (f.size > mb * 1024 * 1024) {
          throw new Error(`${f.name}: ${mb}MB 초과`);
        }
        const r = await uploadSource(pid, f);
        savedCount += r.saved.length;
        skipped = skipped.concat(r.skipped);
      }
      return { savedCount, skipped } as UploadReport;
    },
    onSuccess: async (report) => {
      setError(null);
      setUploadReport(report);
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
    uploadReport,
    upload: (fileList: FileList | null) => {
      if (!fileList || fileList.length === 0) return;
      setError(null);
      setUploadReport(null); // 다음 업로드 시작 시 이전 보고를 클리어
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