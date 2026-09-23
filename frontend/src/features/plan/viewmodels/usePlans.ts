import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { approvePlan, fetchPlans, revisePlan } from "../models/plansApi";
import { errMsg } from "../../../shared/lib/errMsg";

/* plan 세대 목록 + 승인·수정 (FR-2.9, FR-4.3) — 액션은 뮤테이션.
 * 승인/수정 성공 시 목록 무효화 + 새 세대 선택 알림. 포맷 검증 실패(422)도 error로 전달된다. */

export function usePlans(pid: number) {
  const qc = useQueryClient();
  const plansQ = useQuery({ queryKey: ["plans", pid], queryFn: () => fetchPlans(pid) });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const vlabel = (n: number) => `v${String(n).padStart(2, "0")}`;

  async function approve(planId: number) {
    setBusy(true);
    setError(null);
    try {
      const p = await approvePlan(planId);
      setNotice(`plan ${vlabel(p.version_no)} 승인 — 산출물 탭에서 파생물을 생성하세요.`);
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
      setNotice(`plan ${vlabel(p.version_no)} 생성 (새 초안) — 승인해 주세요.`);
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