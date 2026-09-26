import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Job } from "../../../api/client";
import { enqueueReview, fetchJobs, fetchPlans, fetchReviews, reviseFromReview } from "../models/reviewApi";
import { errMsg } from "../../../shared/lib/errMsg";

/* 검수 리포트 (FR-4, FR-5) — 리포트·plan·job 목록 + 검수 실행 + 반영 잡 1회 통지.
 * 검수·반영 잡이 활성인 동안 1.5초 폴링(refetchInterval) — OutputsPanel과 같은 패턴. */

const hasActive = (jobs: Job[]) =>
  jobs.some(
    (j) =>
      (j.type === "review" || j.type === "plan_revise") &&
      (j.status === "queued" || j.status === "running"),
  );

export function useReviews(pid: number) {
  const qc = useQueryClient();
  const reviewsQ = useQuery({ queryKey: ["reviews", pid], queryFn: () => fetchReviews(pid) });
  const plansQ = useQuery({ queryKey: ["plans", pid], queryFn: () => fetchPlans(pid) });
  const jobsQ = useQuery({
    queryKey: ["jobs", pid],
    queryFn: () => fetchJobs(pid),
    refetchInterval: (q) => (hasActive(q.state.data ?? []) ? 1500 : false),
  });

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [reviseDone, setReviseDone] = useState(false);
  const reviseSeenRef = useRef<Set<number>>(new Set());

  const jobs = jobsQ.data ?? [];
  const busy = pending || hasActive(jobs);
  const active = hasActive(jobs);

  // 활성 → 비활성 전환(검수·반영 잡 완료) 시 리포트·plan 갱신 — 원본 폴링 완료 경로 동작 보존
  const prevActiveRef = useRef(false);
  useEffect(() => {
    if (prevActiveRef.current && !active) {
      void qc.invalidateQueries({ queryKey: ["reviews", pid] });
      void qc.invalidateQueries({ queryKey: ["plans", pid] });
    }
    prevActiveRef.current = active;
  }, [active, qc, pid]);

  async function refresh() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["reviews", pid] }),
      qc.invalidateQueries({ queryKey: ["plans", pid] }),
      qc.invalidateQueries({ queryKey: ["jobs", pid] }),
    ]);
  }

  // 반영(revise) 잡 완료/실패 1회 통지 — 검수 잡과 같은 폴링 사이클을 쓴다
  useEffect(() => {
    for (const j of jobs) {
      if (j.type !== "plan_revise" || reviseSeenRef.current.has(j.id)) continue;
      if (j.status === "done") {
        reviseSeenRef.current.add(j.id);
        const res = (j.result ?? {}) as { version_no?: number };
        setNotice(`plan v${res.version_no ?? "?"} 생성 (초안) — plan 탭에서 diff로 검토한 뒤 승인하세요.`);
        setError(null);
        setReviseDone(true);
      } else if (j.status === "failed") {
        reviseSeenRef.current.add(j.id);
        setError(`plan 반영 실패: ${(j.error ?? "원인 불명").split("\n")[0]}`);
      }
    }
  }, [jobs]);

  function enqueue() {
    setError(null);
    setNotice(null);
    setPending(true);
    enqueueReview(pid)
      .then((job) => {
        setNotice(`검수 작업 큐 진입 (#${job.id}) — 워커가 결정론+LLM 검수를 실행합니다.`);
        return refresh();
      })
      .catch((e) => {
        setError(errMsg(e));
      })
      .finally(() => setPending(false));
  }

  return {
    reports: reviewsQ.data ?? null,
    plans: plansQ.data ?? [],
    jobs,
    error,
    notice,
    busy,
    reviseDone,
    enqueue,
  };
}

/** 선택 발견사항 plan 반영 (FR-4.3) — 새 plan 세대(초안) 작성 잡을 큐에 넣는다. */
export function useReviewApply(planId: number, reviewId: number) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function apply(findingIndices: number[]) {
    setBusy(true);
    setErr(null);
    setNotice(null);
    try {
      const job = await reviseFromReview(planId, reviewId, findingIndices);
      setNotice(`plan 반영 작업 큐 진입 (#${job.id}) — 워커가 LLM plan 수정을 실행합니다.`);
    } catch (e) {
      setErr(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  return { busy, err, notice, apply };
}