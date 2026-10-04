import { useQuery, type QueryClient } from "@tanstack/react-query";
import type { Job } from "../../api/client";
import { apiGet } from "../../api/client";
import { errMsg } from "./errMsg";
import { hasActive, latestActive } from "./jobs";

/** 잡 목록 조회 — ["jobs", pid]의 유일한 definition (outputsApi/reviewApi의 중복은 단계 삭제). */
export function fetchJobs(pid: number) {
  return apiGet<Job[]>(`/api/projects/${pid}/jobs`);
}

/** 큐 진입(202) 응답으로 돌아온 잡을 ["jobs", pid] 캐시에 먼저 넣는다 — refetch RTT와
 *  무관하게 큐 카드·busy 게이트가 즉시 반영되고 시딩 잡(queued)이 1.5s 폴링을 켠다.
 *  백엔드는 잡 엔드포인트가 응답 전에 커밋하므로(202 계약) 이후 refetch에도 잡이 포함된다. */
export function seedJob(qc: QueryClient, pid: number, job: Job) {
  qc.setQueryData<Job[]>(["jobs", pid], (old) =>
    old?.some((j) => j.id === job.id) ? old : [...(old ?? []), job]);
}

/** 잡 목록 폴링의 단일 소유자 — ["jobs", pid] 쿼리에 refetchInterval을 붙이는 유일한 관측점.
 *  탭 뷰모델(useOutputs/useReviews)과 헤더(ActivityPill)는 이 훅을 소비만 한다 — interval 없는
 *  관측점은 자체 타이머를 만들지 않는다 (v5 관측점별 refetchInterval 규칙 검증 완료).
 *  주기: 활성 잡 1.5s / 조회 실패 5s 재시도(전역 retry:false 하에서 자가 복구) / idle 정지. */
export function useActiveJobs(pid: number) {
  const jobsQ = useQuery({
    queryKey: ["jobs", pid],
    queryFn: () => fetchJobs(pid),
    enabled: pid > 0,
    refetchInterval: (q) => (q.state.error ? 5000 : hasActive(q.state.data) ? 1500 : false),
  });
  const jobs = jobsQ.data ?? [];
  const activeJob = latestActive(jobs);
  return {
    jobs,
    activeJob,
    active: activeJob !== undefined,
    /** 최초 fetch 도착 여부 — 이미 종료된 잡을 통지에서 제외하는 부트스트랩 게이트용. */
    loaded: jobsQ.data !== undefined,
    /** /jobs 조회 실패 문자열 — 전역 retry:false로 조용히 죽는 것을 화면에 드러낸다. */
    jobsError: jobsQ.isError ? errMsg(jobsQ.error) : null,
  };
}