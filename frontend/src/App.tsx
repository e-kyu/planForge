import { useEffect, useState } from "react";
import { apiGet } from "./api/client";
import { useHashRoute } from "./lib/hashRoute";

/** 상단 앱 바 + 해시 라우트 스위치. 화면은 PR-2~5에서 갈아낀다. */
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

  return (
    <>
      <header className="app-header">
        <h1 className="app-title">report-agent</h1>
        <span className={`health health-${health}`}>
          {health === "ok" ? "API 연결됨" : health === "down" ? "API 연결 안 됨" : "확인 중…"}
        </span>
      </header>
      <main className="app-main">
        <p className="placeholder">
          화면은 M3 PR-2(프로젝트 목록·소스)부터 채워진다. route={route}
        </p>
      </main>
    </>
  );
}