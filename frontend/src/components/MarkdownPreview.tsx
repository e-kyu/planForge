import { useMemo } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";

/** plan.md 미리보기 (§3.1) — 블록 표기법([유형: …] 등)은 WYSIWYG를 쓰지 않으므로
 *  본문 텍스트로 그대로 보인다 (요청서 의도 유지). DOMPurify로 소독한다. */
export function MarkdownPreview({ markdown }: { markdown: string }) {
  const html = useMemo(
    () => DOMPurify.sanitize(marked.parse(markdown, { async: false })),
    [markdown],
  );
  return <div className="md-preview" dangerouslySetInnerHTML={{ __html: html }} />;
}