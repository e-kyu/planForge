import { useCallback, useState } from "react";

/** 화면 표시 환경설정(뷰 프리퍼런스)용 boolean — localStorage pf-* 키. 데이터가 아닌
 *  뷰어 기기 기본값이므로 전역 키(프로젝트별 아님). 접근 불가 시 기본값 사용. */
export function useStoredBoolean(key: string, initial: boolean): [boolean, (v: boolean) => void] {
  const [value, setValue] = useState(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? initial : raw === "1";
    } catch {
      return initial; /* 저장소 접근 불가 — 기본값 */
    }
  });
  const set = useCallback((v: boolean) => {
    setValue(v);
    try {
      localStorage.setItem(key, v ? "1" : "0");
    } catch {
      /* 무시 — 기존 pf-* 패턴과 동일 */
    }
  }, [key]);
  return [value, set];
}