/* 표시용 포맷 유틸 — 버전·날짜/시각·바이트 크기. ui.tsx가 기존 이름을 재수출해
 * 다른 import 경로를 깨지 않는다 (신규 코드는 이 모듈을 직접 쓴다). */

/** 세대·산출물 버전 표기 — `v` + 2자리 zero-pad (`v01`). */
export function formatVersion(n: number): string {
  return `v${String(n).padStart(2, "0")}`;
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** UTC ISO(+00:00) → 로컬 "YYYY-MM-DD HH:mm". 백엔드 UTCDateTime 계약상 +00:00이 실려온다
 * (backend/app/shared/types.py). 기존 `slice(0,16)`은 UTC를 그대로 잘라 허상의 현지시각
 * (한국 저녁 잡이 한낮으로 보임)을 만들었으므로 변환한다 — job #34 사후 대응. 오프셋 없는
 * naive 문자열은 파싱 불가·미래 시각 부정확성을 피해 기존 동작을 유지한다(호환 폴백). */
export function fmtDateTime(iso: string | unknown): string {
  if (typeof iso !== "string") return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.replace("T", " ").slice(0, 16);
  const p = (n: number): string => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** 로컬 날짜 ("YYYY-MM-DD") — 프로젝트 생성일 등 date-only 표기 공용화.
 * (기존 `.slice(0, 10)`은 UTC 날짜를 잘라 한국 저녁 생성 프로젝트가 전날로 표기되는
 * fmtDateTime과 같은 분류의 결함.) */
export function fmtDate(iso: string | unknown): string {
  return fmtDateTime(iso).slice(0, 10);
}

/** epoch 초(예: 소스 st_mtime) → 로컬 "YYYY-MM-DD HH:mm". 소스 목록 등록일시 표기. */
export function formatEpochSeconds(sec: number): string {
  const d = new Date(sec * 1000); // st_mtime — float epoch 초
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
