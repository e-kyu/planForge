import { Check, ChevronRight, FileText, Folder, Trash2 } from "lucide-react";
import { fmtDate } from "../../../shared/components/ui";
import { navigate } from "../../../shared/lib/hashRoute";
import type { DocLoop, Project } from "../../../api/client";

/** 프로젝트 목록의 한 행 + 문서 버튼 (FR-1.1) — 표현 전용. */
export function ProjectRow(props: { p: Project; delBusy: boolean; onDelete: () => void }) {
  const p = props.p;
  const docloops = (p.docloops ?? []) as DocLoop[];
  return (
    <li>
      <button className="project-row" onClick={() => navigate(`/projects/${p.id}`)}>
        <span className="project-top">
          <span className={`badge badge-global badge-${p.status}`}>
            {p.status === "active" ? "진행 중" : "보관"}
          </span>
        </span>
        <span className="project-name">
          <Folder aria-hidden="true" />
          {p.title}
        </span>
        <span className="project-meta">
          {p.slug}
          {p.owner && <span className="project-owner">{p.owner}</span>}
        </span>
        <span className="project-foot">
          <span className="project-date">{fmtDate(p.created_at)}</span>
          <span className="project-open" aria-hidden="true">
            열기
            <ChevronRight />
          </span>
        </span>
      </button>
      {docloops.length > 0 && (
        <div className="project-docs" role="group" aria-label="문서 버튼">
          {docloops.map((l) => (
            <DocButton key={l.doc_slug} p={p} l={l} />
          ))}
        </div>
      )}
      <button
        type="button"
        className="project-del"
        disabled={props.delBusy}
        onClick={props.onDelete}
        aria-label={`${p.title} 삭제`}
        title="삭제"
      >
        <Trash2 aria-hidden="true" />
      </button>
    </li>
  );
}

/** 문서 버튼 — 상태별 동작: locked=비활성(도달 불가 잔여의 안전망), active=인터뷰 진입,
 *  done=plan 탭 진입. 문서는 각각 독립 진행이다 (independent-doc-loops).
 *  라벨 어휘는 백엔드 label 필드 그대로 (프론트 하드코딩 금지 — SSOT는 DOC_KINDS). */
function DocButton({ p, l }: { p: Project; l: DocLoop }) {
  const locked = l.status !== "active" && l.status !== "done";
  const variant = locked
    ? "project-doc-btn-locked"
    : l.status === "done"
      ? "project-doc-btn-done"
      : "project-doc-btn-active";
  const title = locked
    ? `${l.label} — 잠겨 있습니다`
    : l.status === "done"
      ? `${l.label} — plan 승인 완료. plan 탭에서 재작업할 수 있습니다.`
      : `${l.label} — 인터뷰 진입`;
  return (
    <button
      type="button"
      className={`project-doc-btn ${variant}`}
      disabled={locked}
      title={title}
      onClick={
        locked
          ? undefined
          : () =>
              navigate(
                `/projects/${p.id}/${l.doc_slug}/${l.status === "done" ? "plan" : "interview"}`
              )
      }
    >
      {l.status === "done" ? (
        <Check aria-hidden="true" />
      ) : (
        <FileText aria-hidden="true" />
      )}
      {l.label}
      {l.plan_version != null && (
        <span className="project-doc-btn-ver">v{l.plan_version}</span>
      )}
    </button>
  );
}
