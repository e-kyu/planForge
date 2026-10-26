/* 업로드 클라이언트 사전검사 상한 — 서버 상한과 동일하게 유지한다.
 * MAX_SOURCE_MB: 개별 텍스트 소스·개요 문서 (backend MAX_SOURCE_BYTES = 2MB)
 * MAX_ZIP_MB: zip 컨테이너 자체 (backend MAX_ZIP_BYTES = 30MB) — 내부 파일은 2MB 규칙. */
export const MAX_SOURCE_MB = 2;
export const MAX_ZIP_MB = 30;
