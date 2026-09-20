import { useEffect, useState } from "react";
import { CheckCircle2, FileCode, ShieldCheck } from "lucide-react";
import { apiGet } from "../api/client";
import type { Plan, Review } from "../api/client";

type PillTone = "neutral" | "ok" | "warn" | "danger";

type Metrics = {
  planVersion: string | null;
  planStatus: string | null;
  activeFacts: number | null;
  red: number | null;
  yellow: number | null;
};

const EMPTY: Metrics = {
  planVersion: null,
  planStatus: null,
  activeFacts: null,
  red: null,
  yellow: null,
};

/** 헤더 메트릭 필 — 프로젝트 라우트에서만 렌더 (설계 D1).
 *  버튼이 아닌 div만 렌더한다 (e2e `button:has-text('승인')` 오염 방지). */
export default function HeaderMetrics(props: { pid: number }) {
  const [m, setM] = useState<Metrics>(EMPTY);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      const next: Metrics = { ...EMPTY };
      const [plans, facts, reviews] = await Promise.allSettled([
        apiGet<Plan[]>(`/api/projects/${props.pid}/plans`),
        apiGet<{ status: string }[]>(`/api/projects/${props.pid}/facts`),
        apiGet<Review[]>(`/api/projects/${props.pid}/reviews`),
      ]);
      if (plans.status === "fulfilled") {
        const latest = plans.value.at(-1);
        if (latest) {
          next.planVersion = `v${latest.version_no}`;
          next.planStatus = latest.status;
        }
      }
      if (facts.status === "fulfilled") {
        next.activeFacts = facts.value.filter((f) => f.status === "active").length;
      }
      if (reviews.status === "fulfilled") {
        const latest = reviews.value.at(-1);
        if (latest) {
          next.red = latest.red_count;
          next.yellow = latest.yellow_count;
        }
      }
      if (alive) setM(next);
    };
    load();
    const t = setInterval(load, 10_000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [props.pid]);

  const planStatusLabel =
    m.planStatus === "approved"
      ? "승인"
      : m.planStatus === "draft"
        ? "초안"
        : m.planStatus === "superseded"
          ? "대체됨"
          : null;

  const reviewTone: PillTone = m.red == null ? "neutral" : m.red === 0 ? "ok" : "danger";
  const reviewValue =
    m.red == null ? "—" : m.red === 0 && m.yellow === 0 ? "통과" : `🔴${m.red} · 🟡${m.yellow}`;

  return (
    <div className="header-metrics">
      <div className="metric-pill" title="현재 plan 세대 (SSOT)">
        <FileCode />
        <div>
          <div className="metric-label">plan SSOT</div>
          <div className="metric-value">
            {m.planVersion ? `${m.planVersion}${planStatusLabel ? ` · ${planStatusLabel}` : ""}` : "—"}
          </div>
        </div>
      </div>
      <div className="metric-pill" title="확립(활성) 팩트 수">
        <ShieldCheck />
        <div>
          <div className="metric-label">확립 팩트</div>
          <div className="metric-value">{m.activeFacts == null ? "—" : `${m.activeFacts}건`}</div>
        </div>
      </div>
      <div className={`metric-pill metric-${reviewTone}`} title="최근 검수 심각도 (red/yellow)">
        <CheckCircle2 />
        <div>
          <div className="metric-label">최근 검수</div>
          <div className="metric-value">{reviewValue}</div>
        </div>
      </div>
    </div>
  );
}