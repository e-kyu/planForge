import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { approvePlan, fetchPlans, revisePlan } from "../models/plansApi";
import type { DocSlug } from "../../projects/models/docloops";
import { errMsg } from "../../../shared/lib/errMsg";
import { formatVersion } from "../../../shared/lib/format";

/* plan 세대 목록 + 승인·수정 (FR-2.9, FR-4.3) — 액션은 뮤테이션.
 * 승인/수정 성공 시 목록 무효화 + 새 세대 선택 알림. 포맷 검증 실패(422)도 error로 전달된다. */

export function usePlans(pid: number, doc: DocSlug | null = null) {
  const qc = useQueryClient();
  // 문서 라우트에서는 해당 문서의 세대만 조회(?doc_slug=) — 쿼리 키에 doc을 넣어 캐시 분리.
  // ["plans", pid] 프리픽스 무효화는 문서 스코프 캐시도 함께 무효화한다(TanStack 프리픽스 매칭).
  const plansQ = useQuery({
    queryKey: ["plans", pid, doc],
    queryFn: () => fetchPlans(pid, doc),
  });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function approve(planId: number) {
    setBusy(true);
    setError(null);
    try {
      const p = await approvePlan(planId);
      setNotice(`plan ${formatVersion(p.version_no)} 승인 — 산출물 탭에서 파생물을 생성하세요.`);
      await qc.invalidateQueries({ queryKey: ["plans", pid] });
      return p.id;
    } catch (e) {
      setError(errMsg(e));
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function revise(planId: number, markdown: string) {
    setBusy(true);
    setError(null);
    try {
      const p = await revisePlan(planId, markdown);
      setNotice(`plan ${formatVersion(p.version_no)} 생성 (새 초안) — 승인해 주세요.`);
      await qc.invalidateQueries({ queryKey: ["plans", pid] });
      return p.id;
    } catch (e) {
      setError(errMsg(e));
      return null;
    } finally {
      setBusy(false);
    }
  }

  return {
    plans: plansQ.data ?? null,
    error,
    setError,
    notice,
    setNotice,
    busy,
    approve,
    revise,
  };
}