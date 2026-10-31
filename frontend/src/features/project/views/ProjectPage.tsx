import { useEffect, type ComponentType } from "react";
import { ArrowLeft, Bot, FileText, Layout, Layers, ShieldCheck } from "lucide-react";
import { Empty, Loading, fmtDate } from "../../../shared/components/ui";
import { navigate } from "../../../shared/lib/hashRoute";
import type { DocLoop } from "../../../api/client";
import type { DocSlug } from "../../projects/models/docloops";
import type { ProjectTab } from "../models/projectApi";
import { useProject, useTabBadges } from "../viewmodels/useProjectShell";
import SourcesPanel from "../../sources/views/SourcesPanel";
import InterviewPanel from "../../interview/views/InterviewPanel";
import PlanPanel from "../../plan/views/PlanPanel";
import OutputsPanel from "../../outputs/views/OutputsPanel";
import ReviewPanel from "../../review/views/ReviewPanel";

export type { ProjectTab };

const TABS: {
  key: ProjectTab;
  no: number;
  label: string;
  sub?: string;
  icon: ComponentType<{ className?: string }>;
}[] = [
  { key: "sources", no: 1, label: "소스", icon: FileText },
  { key: "interview", no: 2, label: "인터뷰", icon: Bot },
  { key: "plan", no: 3, label: "기획 정의", sub: "plan.md", icon: Layers },
  { key: "outputs", no: 4, label: "산출물", icon: Layout },
  { key: "review", no: 5, label: "검수", icon: ShieldCheck },
];

/** 프로젝트 셸 — 탭 라우팅 (#/projects/:id/:tab, FR-5 화면 구조). 표현 전용 View.
 *  문서 루프 프로젝트(project.docloops 비어 있지 않음)는 doc 칩 행으로 문서별 루프를
 *  표시하고, 레거시 프로젝트(docloops=[])는 기존 화면 그대로다 (step 8). */
export default function ProjectPage({
  pid,
  tab,
  doc = null,
}: {
  pid: number;
  tab: ProjectTab;
  doc?: DocSlug | null;
}) {
  const { project, error } = useProject(pid);
  const badges = useTabBadges(pid);
  const docloops = (project?.docloops ?? []) as DocLoop[];
  const currentLoop = doc ? (docloops.find((l) => l.doc_slug === doc) ?? null) : null;

  // 문서 루프 프로젝트를 문서 미지정(레거시) 라우트로 본 경우 — 현재 active 문서로
  // 리다이렉트(전부 done이면 마지막 문서). 레거시 탭 UI와 문서 루프 흐름의 혼동 방지.
  useEffect(() => {
    if (doc || project === null || docloops.length === 0) return;
    const target = docloops.find((l) => l.status === "active") ?? docloops.at(-1);
    if (target) navigate(`/projects/${pid}/${target.doc_slug}/${tab}`);
  }, [doc, project, docloops, pid, tab]);

  if (error) return <Empty>{error}</Empty>;
  if (project === null) return <Loading />;
  return (
    <>
      <nav className="ws-head" aria-label="프로젝트 정보">
        <button
          type="button"
          className="ws-back"
          onClick={() => navigate("/")}
          aria-label="프로젝트 목록으로 돌아가기"
          title="목록으로 돌아가기"
        >
          <ArrowLeft aria-hidden="true" />
        </button>
        <div className="ws-title">
          <h2>
            {project.title}
            <span className="ws-slug">{project.slug}</span>
          </h2>
          <p className="ws-meta">
            {project.owner ? `담당 ${project.owner} · ` : ""}
            생성일 {fmtDate(project.created_at)}
          </p>
        </div>
      </nav>
      {docloops.length > 0 && (
        <div className="doc-chips" role="group" aria-label="문서 루프">
          {docloops.map((l) => (
            <button
              key={l.doc_slug}
              type="button"
              className={`doc-chip ${doc === l.doc_slug ? "doc-chip-active" : ""}`}
              onClick={() => navigate(`/projects/${pid}/${l.doc_slug}/${tab}`)}
            >
              <span className="doc-chip-label">{l.label}</span>
              <span className={`doc-chip-status doc-status-${l.status}`}>{l.status}</span>
            </button>
          ))}
        </div>
      )}
      <div className="tabs" role="tablist">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              className={`tab ${tab === t.key ? "tab-active" : ""}`}
              onClick={() =>
                navigate(doc ? `/projects/${pid}/${doc}/${t.key}` : `/projects/${pid}/${t.key}`)
              }
            >
              <span className="tab-num">{t.no}</span>
              <Icon aria-hidden="true" />
              {t.label}
              {t.sub && <span className="tab-sub">{t.sub}</span>}
              {badges[t.key] && <span className="tab-badge">{badges[t.key]}</span>}
            </button>
          );
        })}
      </div>
      <section className="tab-body">
        {tab === "sources" && <SourcesPanel pid={pid} />}
        {tab === "interview" &&
          (currentLoop?.status === "locked" ? (
            <Empty>{currentLoop.label} 문서는 잠겨 있어 인터뷰를 시작할 수 없습니다.</Empty>
          ) : (
            <InterviewPanel key={doc ?? "legacy"} pid={pid} doc={doc} />
          ))}
        {tab === "plan" && <PlanPanel pid={pid} doc={doc} />}
        {tab === "outputs" && <OutputsPanel pid={pid} doc={doc} />}
        {tab === "review" && <ReviewPanel pid={pid} doc={doc} />}
      </section>
    </>
  );
}