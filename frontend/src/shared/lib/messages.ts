/* 화면 공용 메시지 문자열 — 기존 문구 그대로 유지한다. */

/** /jobs 조회 실패 안내의 접두 문구. */
export const JOBS_LOAD_ERROR_PREFIX = "작업 상태 조회 실패";

/** 배너·툴팁용 "작업 상태 조회 실패: {원문}". */
export const jobsLoadErrorText = (err: string): string => `${JOBS_LOAD_ERROR_PREFIX}: ${err}`;
