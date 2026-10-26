import { CheckCircle2, FileCode, ShieldCheck } from "lucide-react";
import { useHeaderMetrics } from "../viewmodels/useProjectShell";
import { PLAN_STATUS_SHORT_LABEL } from "../../../shared/lib/labels";

type PillTone = "neutral" | "ok" | "warn" | "danger";

/** plan 세대 표기 — "v03 · 승인" 형태 (상태 라벨이 없으면 버전만). */
function planValue(version: string | null, status: string | null): string {
  if (!version) return "—";
  const label = status ? (PLAN_STATUS_SHORT_LABEL[status] ?? null) : null;
  return `${version}${label ? ` · ${label}` : ""}`;
}

function reviewTone(red: number | null): PillTone {
  if (red == null) return "neutral";
  return red === 0 ? "ok" : "danger";
}

/** 최근 검수 표기 — "통과" 또는 "🔴n · 🟡m". */
function reviewValue(red: number | null, yellow: number | null): string {
  if (red == null) return "—";
  if (red === 0 && yellow === 0) return "통과";
  return `🔴${red} · 🟡${yellow}`;
}

/** 헤더 메트릭 필 — 프로젝트 라우트에서만 렌더 (설계 D1). 데이터는 useHeaderMetrics(10초 폴링).
 *  버튼이 아닌 div만 렌더한다 (e2e `button:has-text('승인')` 오염 방지). */
export default function HeaderMetrics(props: { pid: number }) {
  const m = useHeaderMetrics(props.pid);

  return (
    <div className="header-metrics">
      <div className="metric-pill" title="현재 plan 세대 (SSOT)">
        <FileCode />
        <div>
          <div className="metric-label">plan SSOT</div>
          <div className="metric-value">{planValue(m.planVersion, m.planStatus)}</div>
        </div>
      </div>
      <div className="metric-pill" title="확립(활성) 팩트 수">
        <ShieldCheck />
        <div>
          <div className="metric-label">확립 팩트</div>
          <div className="metric-value">{m.activeFacts == null ? "—" : `${m.activeFacts}건`}</div>
        </div>
      </div>
      <div className={`metric-pill metric-${reviewTone(m.red)}`} title="최근 검수 심각도 (red/yellow)">
        <CheckCircle2 />
        <div>
          <div className="metric-label">최근 검수</div>
          <div className="metric-value">{reviewValue(m.red, m.yellow)}</div>
        </div>
      </div>
    </div>
  );
}