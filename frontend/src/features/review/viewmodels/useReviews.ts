import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Job } from "../../../api/client";
import { enqueueReview, fetchPlans, fetchReviews, reviseFromReview } from "../models/reviewApi";
import { latestByType } from "../../../shared/lib/jobs";
import { seedJob, useActiveJobs } from "../../../shared/lib/useActiveJobs";
import { useTickingNow } from "../../../shared/lib/useTickingNow";
import { errMsg } from "../../../shared/lib/errMsg";

/* 검수 리포트 (FR-4, FR-5) — 리포트·plan·job 목록 + 검수 실행 + 반영 잡 1회 통지.
 * 잡 폴링 소유자는 공용 useActiveJobs (헤더 ActivityPill·OutputsPanel과 같은 캐시) —
 * 검수 탭이 아닐 때도 폴링이 계속된다(헤더가 소유자). */

/** 검수 feature 관점의 활성 판정 — review/plan_revise 타입만 (추적성: 검수 배너 게이트). */
const hasReviewActive = (jobs: Job[]) =>
  jobs.some(
    (j) =>
      (j.type === "review" || j.type === "plan_revise") &&
      (j.status === "queued" || j.status === "running"),
  );

export function useReviews(pid: number) {
  const qc = useQueryClient();
  const reviewsQ = useQuery({ queryKey: ["reviews", pid], queryFn: () => fetchReviews(pid) });
  const plansQ = useQuery({ queryKey: ["plans", pid], queryFn: () => fetchPlans(pid) });
  const jobsS = useActiveJobs(pid);

  // 검수 enqueue API 즉시 실패용 — 반영 잡 실패는 최신 job 객체에서 파생 한다(error 원문 보존)
  const [enqueueError, setEnqueueError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [reviseDone, setReviseDone] = useState(false);
  const reviseSeenRef = useRef<Set<number>>(new Set());
  const bootstrappedRef = useRef(false);

  const jobs = jobsS.jobs;
  const busy = pending || hasReviewActive(jobs);
  const active = hasReviewActive(jobs);
  // 경과 갱신 틱 — 조건은 some(running) (activeJob 기준이면 여러 잡일 때 멈춘다)
  const now = useTickingNow(jobs.some((j) => j.status === "running"));

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

  // 반영(revise) 잡 완료 1회 통지 — 검수 잡과 같은 폴링 사이클을 쓴다.
  // 실패 배너는 state가 아니라 최신 job 상태에서 파생(reviseError) — 과거 실패 잔존 방지.
  useEffect(() => {
    // 첫 데이터 도착 시 이미 종료된 plan_revise 잡은 통지 대상에서 제외 — 탭 재진입 재표시 방지
    if (jobsS.loaded && !bootstrappedRef.current) {
      bootstrappedRef.current = true;
      for (const j of jobs) {
        if (j.type === "plan_revise" && j.status !== "queued" && j.status !== "running") {
          reviseSeenRef.current.add(j.id);
        }
      }
    }
    for (const j of jobs) {
      if (j.type !== "plan_revise" || reviseSeenRef.current.has(j.id)) continue;
      if (j.status === "done") {
        reviseSeenRef.current.add(j.id);
        const res = (j.result ?? {}) as { version_no?: number };
        setNotice(`plan v${res.version_no ?? "?"} 생성 (초안) — plan 탭에서 diff로 검토한 뒤 승인하세요.`);
        setReviseDone(true);
      } else if (j.status === "failed") {
        reviseSeenRef.current.add(j.id);
      }
    }
  }, [jobs, jobsS.loaded]);

  // 마지막 반영 잡이 실패한 경우에만 배너 — 새 잡이 큐에 들어오면 자동 소멸.
  // 문자열 가공은 View 공용 JobErrorDetail이 담당하므로 job 객체만 흘린다 (결정 16).
  const latestRevise = useMemo(() => latestByType(jobs, "plan_revise"), [jobs]);
  const failedReviseJob = useMemo(
    () => (latestRevise && latestRevise.status === "failed" ? latestRevise : null),
    [latestRevise],
  );

  function enqueue() {
    setEnqueueError(null);
    setNotice(null);
    setPending(true);
    enqueueReview(pid)
      .then((job) => {
        setNotice(`검수 작업 큐 진입 (#${job.id}) — 워커가 결정론+LLM 검수를 실행합니다.`);
        seedJob(qc, pid, job);
        return refresh();
      })
      .catch((e) => {
        setEnqueueError(errMsg(e));
      })
      .finally(() => setPending(false));
  }

  return {
    reports: reviewsQ.data ?? null,
    plans: plansQ.data ?? [],
    jobs,
    jobsError: jobsS.jobsError,
    now,
    error: enqueueError,
    failedReviseJob,
    notice,
    busy,
    reviseDone,
    enqueue,
  };
}

/** 선택 발견사항 plan 반영 (FR-4.3) — 새 plan 세대(초안) 작성 잡을 큐에 넣는다. */
export function useReviewApply(planId: number, reviewId: number, pid: number) {
  const qc = useQueryClient();
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
      // jobs 갱신 — 시딩으로 최신 revise 잡(queued)이 즉시 목록에 들어오며 과거 실패
      // 파생 배너가 소멸하고, invalidate-refetch가 서버 목록으로 확정한다
      seedJob(qc, pid, job);
      void qc.invalidateQueries({ queryKey: ["jobs", pid] });
    } catch (e) {
      setErr(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  return { busy, err, notice, apply };
}