import { useQuery } from "@tanstack/react-query";
import type { Plan, Review } from "../../../api/client";
import { fetchHeaderMetrics, fetchProject, fetchTabBadges } from "../models/projectApi";
import type { ProjectTab } from "../models/projectApi";
import { errMsg } from "../../../shared/lib/errMsg";

/* 프로젝트 셸 데이터 — 단일 프로젝트, 탭 배지, 헤더 메트릭 (§2 ViewModel). */

/** 프로젝트 한 건 — 셸 표시(제목·슬러그·생성일)용. */
export function useProject(pid: number) {
  const projectQ = useQuery({
    queryKey: ["project", pid],
    queryFn: () => fetchProject(pid),
    retry: false,
  });
  return {
    project: projectQ.data ?? null,
    error: projectQ.isError ? errMsg(projectQ.error) : null,
  };
}

export type Badges = Partial<Record<ProjectTab, string>>;

/** 탭 카운트 배지 — 마운트 시 1회 수집 (설계 D9). plan 배지는 vNN만 ('승인' 문자열 금지). */
export function useTabBadges(pid: number): Badges {
  const badgesQ = useQuery({
    queryKey: ["tab-badges", pid],
    queryFn: async () => {
      const [sources, facts, plans, builds, reviews] = await fetchTabBadges(pid);
      const badges: Badges = {};
      if (sources.status === "fulfilled") badges.sources = `${sources.value.length}`;
      if (facts.status === "fulfilled")
        badges.interview = `${facts.value.filter((f) => f.status === "active").length}`;
      if (plans.status === "fulfilled" && plans.value.length > 0) {
        const latest = plans.value.at(-1);
        if (latest) badges.plan = `v${String(latest.version_no).padStart(2, "0")}`;
      }
      if (builds.status === "fulfilled") badges.outputs = `${builds.value.length}`;
      if (reviews.status === "fulfilled") {
        const latest = reviews.value.at(-1);
        if (latest)
          badges.review =
            latest.red_count === 0 && latest.yellow_count === 0 ? "통과" : `🔴${latest.red_count}`;
      }
      return badges;
    },
    staleTime: Infinity, // D9 — 마운트 시 1회 수집
  });
  return badgesQ.data ?? {};
}

/** 헤더 메트릭 (설계 D1) — 10초 폴링. 부분 실패는 "—" 표시로 살아남는다(allSettled). */
export function useHeaderMetrics(pid: number) {
  const metricsQ = useQuery({
    queryKey: ["header-metrics", pid],
    queryFn: () => fetchHeaderMetrics(pid),
    refetchInterval: 10_000,
  });

  const [plans, facts, reviews] = metricsQ.data ?? [null, null, null];
  const latestPlan: Plan | undefined = (plans?.status === "fulfilled" ? plans.value : [])?.at(-1);
  const latestReview: Review | undefined =
    (reviews?.status === "fulfilled" ? reviews.value : [])?.at(-1);
  const activeFacts: number | null =
    facts?.status === "fulfilled"
      ? facts.value.filter((f) => f.status === "active").length
      : null;

  return {
    planVersion: latestPlan ? `v${latestPlan.version_no}` : null,
    planStatus: latestPlan?.status ?? null,
    activeFacts,
    red: latestReview?.red_count ?? null,
    yellow: latestReview?.yellow_count ?? null,
  };
}