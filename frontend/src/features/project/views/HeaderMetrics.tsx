import { CheckCircle2, FileCode, ShieldCheck } from "lucide-react";
import { useHeaderMetrics } from "../viewmodels/useProjectShell";

type PillTone = "neutral" | "ok" | "warn" | "danger";

/** 헤더 메트릭 필 — 프로젝트 라우트에서만 렌더 (설계 D1). 데이터는 useHeaderMetrics(10초 폴링).
 *  버튼이 아닌 div만 렌더한다 (e2e `button:has-text('승인')` 오염 방지). */
export default function HeaderMetrics(props: { pid: number }) {
  const m = useHeaderMetrics(props.pid);

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