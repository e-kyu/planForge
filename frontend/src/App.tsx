import { useEffect, useState, type ReactNode } from "react";
import { Bot } from "lucide-react";
import { apiGet } from "./api/client";
import { routeParam, useHashRoute } from "./lib/hashRoute";
import HeaderMetrics from "./components/HeaderMetrics";
import ProjectsPage from "./pages/ProjectsPage";
import ProjectPage, { type ProjectTab } from "./pages/ProjectPage";

const TAB_KEYS = new Set(["interview", "plan", "outputs", "review", "sources"]);

/** 상단 앱 바 + 해시 라우트:
 *  #/                     → 프로젝트 목록 (FR-1.1)
 *  #/projects/:id/:tab    → 프로젝트 셸 (FR-5) */
export default function App() {
  const route = useHashRoute();
  const [health, setHealth] = useState<"ok" | "down" | "checking">("checking");

  useEffect(() => {
    let alive = true;
    apiGet<{ status: string }>("/api/health")
      .then((h) => alive && setHealth(h.status === "ok" ? "ok" : "down"))
      .catch(() => alive && setHealth("down"));
    return () => {
      alive = false;
    };
  }, []);

  // 헤더 메트릭은 프로젝트 라우트에서만 (설계 D1 — pid 파싱은 라우팅과 동일 규칙)
  const pid = route.startsWith("/projects") ? Number(routeParam(route, 2)) : 0;
  const tabParam = routeParam(route, 3);
  const hasTab = Boolean(tabParam && TAB_KEYS.has(tabParam));

  let body: ReactNode;
  if (route === "/" || route.startsWith("/projects")) {
    const tab = (tabParam && TAB_KEYS.has(tabParam) ? tabParam : "interview") as ProjectTab;
    body = pid > 0 && hasTab ? (
      <ProjectPage pid={pid} tab={tab} />
    ) : pid > 0 ? (
      // #/projects/:id → 기본 탭으로 치환
      <ProjectRedirect pid={pid} />
    ) : (
      <ProjectsPage />
    );
  } else {
    body = <p className="hint">알 수 없는 경로: {route}</p>;
  }

  return (
    <>
      <header className="app-header">
        <a className="brand" href="#/">
          <span className="brand-chip" aria-hidden="true">
            <Bot />
          </span>
          <h1 className="app-title">report-agent</h1>
        </a>
        <span className="spacer" />
        {pid > 0 && hasTab && <HeaderMetrics pid={pid} />}
        <span className={`health health-${health}`}>
          {health === "ok" ? "API 연결됨" : health === "down" ? "API 연결 안 됨" : "확인 중…"}
        </span>
      </header>
      <main className="app-main">{body}</main>
    </>
  );
}

function ProjectRedirect({ pid }: { pid: number }) {
  useEffect(() => {
    window.location.replace(`#/projects/${pid}/interview`);
  }, [pid]);
  return null;
}