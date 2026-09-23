import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../../api/client";

/** API 헬스 확인 — App 셸 표시용 (10초 폴링은 header-metrics가 담당, 여기선 최초 1회). */
export function useApiHealth(): "ok" | "down" | "checking" {
  const healthQ = useQuery({
    queryKey: ["health"],
    queryFn: () => apiGet<{ status: string }>("/api/health"),
    staleTime: Infinity,
    retry: false,
  });
  if (healthQ.isPending) return "checking";
  return healthQ.data?.status === "ok" ? "ok" : "down";
}