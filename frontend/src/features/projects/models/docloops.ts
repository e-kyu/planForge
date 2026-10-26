/** 문서 루프 슬러그 — 백엔드 docloops DOC_KINDS와 동기 (SSOT는 백엔드,
 *  app/modules/docloops/application/service.py). 순서는 목차·표시 순서일 뿐 —
 *  문서는 각각 독립 진행이다 (independent-doc-loops). */
export const DOC_SLUGS = ["proposal", "uiux-design", "dev-design"] as const;
export type DocSlug = (typeof DOC_SLUGS)[number];

/** 라우트 구간이 문서 슬러그인지 — 레거시 탭 키와 DOC_SLUGS는 겹치지 않는다. */
export function isDocSlug(s: string | null): s is DocSlug {
  return s !== null && (DOC_SLUGS as readonly string[]).includes(s);
}