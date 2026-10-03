import { useEffect, useState } from "react";

/** 1초 틱 시각 공급 — 활성 잡 경과(elapsedText) 갱신 전용.
 *  TanStack structural sharing은 폴링 페이로드가 동일하면 리렌더를 일으키지 않으므로
 *  (진행 기록 사이 구간이 항상 동일) 경과시간이 멈춘다 — 이 틱이 그 간극을 채운다.
 *  enabled=false면 타이머 없음·리렌더 없음 (idle에서 CPU 소모 없음). */
export function useTickingNow(enabled: boolean, intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(timer);
  }, [enabled, intervalMs]);
  return now;
}