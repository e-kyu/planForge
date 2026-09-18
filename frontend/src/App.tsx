import { useEffect, useState } from "react";
import { apiGet } from "./api/client";
import { routeParam, useHashRoute } from "./lib/hashRoute";
import ProjectsPage from "./pages/ProjectsPage";
import ProjectPage, { type ProjectTab } from "./pages/ProjectPage";

const TAB_KEYS = new Set(["interview", "plan", "outputs", "sources"]);

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

  let body: React.ReactNode;
  if (route === "/" || route.startsWith("/projects")) {
    const pid = Number(routeParam(route, 2));
    const tabParam = routeParam(route, 3);
    const tab = (tabParam && TAB_KEYS.has(tabParam) ? tabParam : "interview") as ProjectTab;
    body = pid > 0 && tabParam ? (
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
        <a className="app-home" href="#/">
          <h1 className="app-title">report-agent</h1>
        </a>
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