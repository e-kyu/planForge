import type { Plan } from "../../api/client";

/* plan 목록 파생 셀렉터 — outputs·review feature 공용. */

/** 최신 승인 plan — 목록 뒤에서부터 찾는다(list_plans가 세대 오름차순 반환).
 *  doc을 주면 해당 문서(doc_slug)의 승인 plan만 고른다. doc 생략·null이면 문서 무관
 *  (OutputsPanel — 조회 자체가 doc 스코프 / ReviewPanel — doc 미지정 레거시 라우트). */
export function latestApproved(plans: Plan[], doc?: string | null): Plan | undefined {
  for (let i = plans.length - 1; i >= 0; i--) {
    const p = plans[i]!;
    if (p.status === "approved" && (doc == null || p.doc_slug === doc)) return p;
  }
  return undefined;
}
