import { useEffect, useState, type ComponentType } from "react";
import { ArrowLeft, Bot, FileText, Layout, Layers, ShieldCheck } from "lucide-react";
import { apiGet, ApiError, type Project } from "../api/client";
import { Empty, Loading } from "../components/ui";
import { navigate } from "../lib/hashRoute";
import SourcesPanel from "./SourcesPanel";
import InterviewPanel from "./InterviewPanel";
import PlanPanel from "./PlanPanel";
import OutputsPanel from "./OutputsPanel";
import ReviewPanel from "./ReviewPanel";

export type ProjectTab = "interview" | "plan" | "outputs" | "review" | "sources";

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

type Badges = Partial<Record<ProjectTab, string>>;

/** 탭 카운트 배지 — 마운트 시 1회 수집 (설계 D9). plan 배지는 vNN만 ('승인' 문자열 금지). */
function useTabBadges(pid: number): Badges {
  const [badges, setBadges] = useState<Badges>({});
  useEffect(() => {
    let alive = true;
    void (async () => {
      const [sources, facts, plans, builds, reviews] = await Promise.allSettled([
        apiGet<{ name: string }[]>(`/api/projects/${pid}/sources`),
        apiGet<{ status: string }[]>(`/api/projects/${pid}/facts`),
        apiGet<{ id: number; version_no: number }[]>(`/api/projects/${pid}/plans`),
        apiGet<{ id: number }[]>(`/api/projects/${pid}/outputs`),
        apiGet<{ red_count: number; yellow_count: number }[]>(`/api/projects/${pid}/reviews`),
      ]);
      if (!alive) return;
      const next: Badges = {};
      if (sources.status === "fulfilled")
        next.sources = `${sources.value.length}`;
      if (facts.status === "fulfilled")
        next.interview = `${facts.value.filter((f) => f.status === "active").length}`;
      if (plans.status === "fulfilled" && plans.value.length > 0) {
        const latest = plans.value.at(-1);
        if (latest) next.plan = `v${String(latest.version_no).padStart(2, "0")}`;
      }
      if (builds.status === "fulfilled") next.outputs = `${builds.value.length}`;
      if (reviews.status === "fulfilled") {
        const latest = reviews.value.at(-1);
        if (latest) next.review = latest.red_count === 0 && latest.yellow_count === 0 ? "통과" : `🔴${latest.red_count}`;
      }
      setBadges(next);
    })();
    return () => {
      alive = false;
    };
  }, [pid]);
  return badges;
}

/** 프로젝트 셸 — 탭 라우팅 (#/projects/:id/:tab, FR-5 화면 구조). */
export default function ProjectPage({ pid, tab }: { pid: number; tab: ProjectTab }) {
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  const badges = useTabBadges(pid);

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