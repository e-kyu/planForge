/* 화면 상태 라벨의 단일 어휘 — 기존 화면 문구를 그대로 옮겼다.
 * 서로 다른 문구(예: plan `승인됨` vs 헤더약어 `승인`)는 이번 단계에서 통일하지 않고
 * 각각의 키를 유지한다 — 화면별 표기 의도가 다르다. */

/** plan 세대 상태 — plan 목록 배지(PlanPanel). */
export const PLAN_STATUS_LABEL: Record<string, string> = {
  draft: "초안",
  approved: "승인됨",
  superseded: "이전 버전",
};

/** plan 세대 상태 약어 — 헤더 메트릭(HeaderMetrics). 목록 배지와 문구가 다르다. */
export const PLAN_STATUS_SHORT_LABEL: Record<string, string> = {
  draft: "초안",
  approved: "승인",
  superseded: "이전 버전",
};

/** job 상태 — 아이콘·라벨(작업 큐). */
export const JOB_STATUS_LABEL: Record<string, { icon: string; label: string }> = {
  queued: { icon: "○", label: "대기" },
  running: { icon: "⟳", label: "진행" },
  done: { icon: "✓", label: "완료" },
  failed: { icon: "✕", label: "실패" },
  cancelled: { icon: "−", label: "취소" },
};
