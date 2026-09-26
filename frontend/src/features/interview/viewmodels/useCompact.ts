import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { CompactApplyResult, CompactPreview } from "../../../api/client";
import { applyCompact, fetchActiveFacts, proposeCompact } from "../models/factsApi";
import { errMsg } from "../../../shared/lib/errMsg";

/* 팩트 압축 (FR-6.1, compact-log 이식) — LLM 통합 제안 → 승인 → 아카이브 적용. */

export function useCompact(pid: number) {
  const qc = useQueryClient();
  const factsQ = useQuery({ queryKey: ["facts", pid, "active"], queryFn: () => fetchActiveFacts(pid) });

  const [preview, setPreview] = useState<CompactPreview | null>(null);
  const [result, setResult] = useState<CompactApplyResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function propose() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setPreview(await proposeCompact(pid));
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  const applyM = useMutation({
    mutationFn: (groups: unknown) => applyCompact(pid, groups),
    onSuccess: async (r) => {
      setResult(r);
      setPreview(null);
      await qc.invalidateQueries({ queryKey: ["facts", pid] });
    },
    onError: (e) => setError(errMsg(e)),
    onSettled: () => setBusy(false),
  });

  function apply() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    applyM.mutate(preview.groups);
  }

  return {
    facts: factsQ.data ?? null,
    preview,
    result,
    busy,
    error,
    propose,
    apply,
    close: () => setPreview(null),
  };
}