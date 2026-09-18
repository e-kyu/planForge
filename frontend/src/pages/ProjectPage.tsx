import { useEffect, useState } from "react";
import { apiGet, ApiError, type Project } from "../api/client";
import { Empty, Loading } from "../components/ui";
import { navigate } from "../lib/hashRoute";
import SourcesPanel from "./SourcesPanel";
import InterviewPanel from "./InterviewPanel";
import PlanPanel from "./PlanPanel";
import OutputsPanel from "./OutputsPanel";

export type ProjectTab = "interview" | "plan" | "outputs" | "sources";

const TABS: { key: ProjectTab; label: string }[] = [
  { key: "interview", label: "인터뷰" },
  { key: "plan", label: "plan.md" },
  { key: "outputs", label: "산출물" },
  { key: "sources", label: "소스" },
];

/** 프로젝트 셸 — 탭 라우팅 (#/projects/:id/:tab, FR-5 화면 구조). */
export default function ProjectPage({ pid, tab }: { pid: number; tab: ProjectTab }) {
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Project>(`/api/projects/${pid}`)
      .then((p) => {
        setProject(p);
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [pid]);

  if (error) return <Empty>{error}</Empty>;
  if (project === null) return <Loading />;
  return (
    <>
      <nav className="crumbs">
        <a href="#/">프로젝트</a>
        <span> / </span>
        <span>{project.title}</span>
      </nav>
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            className={`tab ${tab === t.key ? "tab-active" : ""}`}
            onClick={() => navigate(`/projects/${pid}/${t.key}`)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <section className="tab-body">
        {tab === "sources" && <SourcesPanel pid={pid} />}
        {tab === "interview" && <InterviewPanel pid={pid} />}
        {tab === "plan" && <PlanPanel pid={pid} />}
        {tab === "outputs" && <OutputsPanel pid={pid} />}
      </section>
    </>
  );
}