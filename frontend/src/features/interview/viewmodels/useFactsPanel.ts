import { useQuery } from "@tanstack/react-query";
import { fetchFacts } from "../models/factsApi";
import { errMsg } from "../../../shared/lib/errMsg";

/* 팩트 저장소 사이드 패널 데이터 (설계 D4 — 조회 전용).
 * 확립/미확정/아카이브 필터링은 View의 표시 로직이므로 여기선 전체 목록만 제공한다.
 * 인터뷰 턴 종료 시 useInterview가 ["facts", pid]를 무효화하면 이 쿼리가 갱신된다. */

export function useFactsPanel(pid: number) {
  const factsQ = useQuery({ queryKey: ["facts", pid], queryFn: () => fetchFacts(pid) });
  return {
    facts: factsQ.data ?? null,
    error: factsQ.isError ? errMsg(factsQ.error) : null,
  };
}