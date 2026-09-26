import type { ComponentType } from "react";
import { ArrowLeft, Bot, FileText, Layout, Layers, ShieldCheck } from "lucide-react";
import { Empty, Loading } from "../../../shared/components/ui";
import { navigate } from "../../../shared/lib/hashRoute";
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
  { key: "plan", no: 3, label: "계획정의", sub: "plan.md", icon: Layers },
  { key: "outputs", no: 4, label: "산출물", icon: Layout },
  { key: "review", no: 5, label: "검수", icon: ShieldCheck },
];

/** 프로젝트 셸 — 탭 라우팅 (#/projects/:id/:tab, FR-5 화면 구조). 표현 전용 View. */
export default function ProjectPage({ pid, tab }: { pid: number; tab: ProjectTab }) {
  const { project, error } = useProject(pid);
  const badges = useTabBadges(pid);

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
            생성일 {project.created_at.slice(0, 10)}
          </p>
        </div>
      </nav>
      <div className="tabs" role="tablist">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              className={`tab ${tab === t.key ? "tab-active" : ""}`}
              onClick={() => navigate(`/projects/${pid}/${t.key}`)}
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
        {tab === "interview" && <InterviewPanel pid={pid} />}
        {tab === "plan" && <PlanPanel pid={pid} />}
        {tab === "outputs" && <OutputsPanel pid={pid} />}
        {tab === "review" && <ReviewPanel pid={pid} />}
      </section>
    </>
  );
}