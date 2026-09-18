import { useEffect, useState } from "react";

/** 의존성 없는 해시 라우터 — M3 화면 규모(5개 화면)에 충분. */
export function useHashRoute(): string {
  const [hash, setHash] = useState(() => window.location.hash.slice(1) || "/");
  useEffect(() => {
    const on = () => setHash(window.location.hash.slice(1) || "/");
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash;
}

export function navigate(to: string): void {
  window.location.hash = to;
}

export function routeParam(route: string, index: number): string | null {
  return route.split("/")[index] ?? null;
}