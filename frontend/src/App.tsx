import { useEffect, type ReactNode } from "react";
import { Bot } from "lucide-react";
import { routeParam, useHashRoute } from "./shared/lib/hashRoute";
import { useApiHealth } from "./shared/lib/useApiHealth";
import HeaderMetrics from "./features/project/views/HeaderMetrics";
import ActivityPill from "./features/project/views/ActivityPill";
import ProjectsPage from "./features/projects/views/ProjectsPage";
import ProjectPage, { type ProjectTab } from "./features/project/views/ProjectPage";
import { isDocSlug, type DocSlug } from "./features/projects/models/docloops";

const TAB_KEYS = new Set(["interview", "plan", "outputs", "review", "sources"]);

function isTabKey(s: string | null): s is ProjectTab {
  return s !== null && TAB_KEYS.has(s);
}

/** 상단 앱 바 + 해시 라우트:
 *  #/                     → 프로젝트 목록 (FR-1.1)
 *  #/projects/:id/:tab    → 프로젝트 셸 — 레거시 라우트 (doc=null) (FR-5)
 *  #/projects/:id/:docSlug/:tab → 문서 루프 셸 (seg3가 DOC_SLUGS 원소일 때 — 레거시 탭 키 우선) */
export default function App() {
  const route = useHashRoute();
  const health = useApiHealth();

  // 헤더 메트릭은 프로젝트 라우트에서만 (설계 D1 — pid 파싱은 라우팅과 동일 규칙)
  const pid = route.startsWith("/projects") ? Number(routeParam(route, 2)) : 0;
  // 라우트 해석 — seg3가 기존 탭 키면 레거시 그대로(doc=null), DOC_SLUGS 원소면 문서 라우트
  // (기존 탭 키와 DOC_SLUGS는 겹치지 않으므로 충돌 없음 — 레거시 우선).
  const seg3 = routeParam(route, 3);
  const seg4 = routeParam(route, 4);
  const legacyTab = isTabKey(seg3) ? seg3 : null;
  const doc = !legacyTab && isDocSlug(seg3) && isTabKey(seg4) ? seg3 : null;
  const tab = legacyTab ?? (doc ? (seg4 as ProjectTab) : null);

  let body: ReactNode;
  if (route === "/" || route.startsWith("/projects")) {
    body = pid > 0 && tab ? (
      <ProjectPage pid={pid} tab={tab} doc={doc} />
    ) : pid > 0 ? (
      // 레거시 #/projects/:id, 또는 문서 슬러그 뒤 탭 누락(#/projects/:id/:docSlug) → 기본 탭 치환
      <ProjectRedirect pid={pid} doc={isDocSlug(seg3) ? seg3 : undefined} />
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
          <h1 className="app-title">PlanForge</h1>
        </a>
        <span className="spacer" />
        {pid > 0 && tab && <ActivityPill pid={pid} />}
        {pid > 0 && tab && <HeaderMetrics pid={pid} />}
        <span className={`health health-${health}`}>
          {health === "ok" ? "API 연결됨" : health === "down" ? "API 연결 안 됨" : "확인 중…"}
        </span>
      </header>
      <main className="app-main">{body}</main>
    </>
  );
}

function ProjectRedirect({ pid, doc }: { pid: number; doc?: DocSlug }) {
  useEffect(() => {
    window.location.replace(
      doc ? `#/projects/${pid}/${doc}/sources` : `#/projects/${pid}/sources`,
    );
  }, [pid, doc]);
  return null;
}