import { useActiveJobs } from "../../../shared/lib/useActiveJobs";
import { useTickingNow } from "../../../shared/lib/useTickingNow";
import { jobStateText, queuedStateText } from "../../../shared/lib/jobs";

/** 전역 작업 필 — 다른 탭(인터뷰/plan/소스)에서도 파생물·검수 잡 진행을 보게 한다.
 *  탭 패널은 하나씩만 마운트되므로, 폴링 소유자(useActiveJobs의 refetchInterval)를
 *  이 컴포넌트가 유지 — 탭 전환과 무관하게 폴링이 계속된다. idle이면 문구가 없어
 *  렌더를 null로 (마운트는 유지). 헤더 메트릭과 같이 버튼이 아닌 div만 렌더한다
 *  (e2e `button:has-text('...')` 오염 방지 — HeaderMetrics 주석 참조). */
export default function ActivityPill({ pid }: { pid: number }) {
  const { jobs, activeJob, jobsError } = useActiveJobs(pid);
  // 틱 조건은 some(running) — 직렬 워커는 최오부 잡을 running, latestActive는 최신
  // queued를 가리키므로 activeJob.status 기준이면 두 잡 이상일 때 틱이 멈춘다.
  const now = useTickingNow(jobs.some((j) => j.status === "running"));

  if (!activeJob && !jobsError) return null;

  // 활성 잡이 있으면 진행 문구, 없으면 조회 실패(danger). 활성 잡 노출 우선 —
  // 실패 중에도 마지막 알고 있던 진행을 보여주는 편이 상태 추적에 유리하다.
  if (activeJob) {
    const running = activeJob.status === "running";
    const text =
      activeJob.status === "queued"
        ? queuedStateText(activeJob)
        : (jobStateText(activeJob, now) ?? "처리 중");
    return (
      <div className="activity-pill" title={jobsError ? `작업 상태 조회 실패: ${jobsError}` : text}>
        <span className={`activity-dot ${running ? "activity-dot-pulse" : ""}`} aria-hidden="true" />
        <span className="activity-text">{text}</span>
      </div>
    );
  }

  return (
    <div className="activity-pill activity-pill-danger" title={jobsError ?? ""}>
      <span className="activity-dot" aria-hidden="true" />
      <span className="activity-text">작업 상태 조회 실패</span>
    </div>
  );
}