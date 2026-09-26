import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Build, Job } from "../../../api/client";
import { enqueueDerivative, fetchBuilds, fetchJobs, fetchOutputText, fetchPlans } from "../models/outputsApi";
import { errMsg } from "../../../shared/lib/errMsg";

/* 산출물 갤러리 (FR-3.4/3.5, FR-5) — 갤러리·작업 큐·미리보기 데이터.
 * 활성 job(queued/running)이 있는 동안 jobs 쿼리를 1.5초 간격으로 폴링하고,
 * 큐가 비워지면(완료) 갤러리·plan 쿼리를 무효화해 갱신한다 — 원본 폴링의 완료 경로
 * (마지막 load()에서 갤러리까지 재조회)에 해당한다. */

const hasActive = (jobs: Job[] | undefined) =>
  Boolean(jobs?.some((j) => j.status === "queued" || j.status === "running"));

export function useOutputs(pid: number) {
  const qc = useQueryClient();
  const buildsQ = useQuery({ queryKey: ["builds", pid], queryFn: () => fetchBuilds(pid) });
  const plansQ = useQuery({ queryKey: ["plans", pid], queryFn: () => fetchPlans(pid) });
  const jobsQ = useQuery({
    queryKey: ["jobs", pid],
    queryFn: () => fetchJobs(pid),
    refetchInterval: (q) => (hasActive(q.state.data) ? 1500 : false),
  });

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [sel, setSel] = useState<Build | null>(null);
  const [selPreview, setSelPreview] = useState<string | null>(null);

  const jobs = jobsQ.data ?? [];
  const queueBusy = pending || hasActive(jobs);
  const active = hasActive(jobs);

  // 활성 → 비활성 전환(잡 완료) 시 갤러리·plan 갱신 — 원본 폴링 완료 경로 동작 보존
  const prevActiveRef = useRef(false);
  useEffect(() => {
    if (prevActiveRef.current && !active) {
      void qc.invalidateQueries({ queryKey: ["builds", pid] });
      void qc.invalidateQueries({ queryKey: ["plans", pid] });
    }
    prevActiveRef.current = active;
  }, [active, qc, pid]);

  async function refresh() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["builds", pid] }),
      qc.invalidateQueries({ queryKey: ["plans", pid] }),
      qc.invalidateQueries({ queryKey: ["jobs", pid] }),
    ]);
  }

  const enqueueM = useMutation({
    mutationFn: (body: { kind: "slides" | "report"; doc?: string; fmts?: string[] }) =>
      enqueueDerivative(pid, body),
    onSuccess: async (job) => {
      setNotice(`작업 큐 진입 (#${job.id}) — 워커가 직렬 처리합니다.`);
      await refresh();
    },
    onError: (e) => {
      setError(errMsg(e));
      setPending(false);
    },
    onSettled: () => setPending(false),
  });

  function enqueue(kind: "slides" | "report", doc: string | undefined, fmts?: string[]) {
    setError(null);
    setNotice(null);
    setPending(true);
    enqueueM.mutate({ kind, doc, fmts });
  }

  /** 미리보기 선택 — md는 본문을 당겨오고, 나머지 확장자는 프레임만 연다. */
  async function preview(b: Build) {
    setSel(b);
    setSelPreview(null);
    if (b.ext === "md") {
      try {
        setSelPreview(await fetchOutputText(pid, b.id));
      } catch {
        setSelPreview("(미리보기를 읽지 못했습니다)");
      }
    }
  }

  function closePreview() {
    setSel(null);
  }

  return {
    builds: buildsQ.data ?? null,
    plans: plansQ.data ?? [],
    jobs,
    error,
    notice,
    busy: queueBusy,
    enqueue,
    preview,
    sel,
    selPreview,
    closePreview,
  };
}