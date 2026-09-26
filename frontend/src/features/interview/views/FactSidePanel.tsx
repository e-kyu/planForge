import { useRef, useState } from "react";
import { Database, PanelRightClose, PanelRightOpen } from "lucide-react";
import type { Fact } from "../../../api/client";
import { Banner } from "../../../shared/components/ui";
import { useFactsPanel } from "../viewmodels/useFactsPanel";

const FACT_FILTERS = [
  { id: "all", label: "전체" },
  { id: "active", label: "확립" },
  { id: "unconfirmed", label: "미확정" },
  { id: "archived", label: "아카이브" },
] as const;
type FactFilter = (typeof FACT_FILTERS)[number]["id"];

const ORIGIN_LABEL: Record<string, string> = {
  interview: "인터뷰",
  review: "검수",
  manual: "수동",
};

/** 팩트 저장소 사이드 패널 — 조회 전용 (설계 D4).
 *  확정은 인터뷰 게이트(FactGate → POST /facts/confirm)에서만 수행된다(원칙 4 게이트 우회 금지).
 *  미확정 필터는 백엔드 UNCONFIRMED 컨벤션("(미확정" 접두 마커)과 동일한 클라이언트 판별(설계 D5). */
export function FactSidePanel({
  pid,
  collapsed,
  onToggle,
}: {
  pid: number;
  collapsed: boolean;
  onToggle: () => void;
}) {
  const { facts, error } = useFactsPanel(pid);
  const [filter, setFilter] = useState<FactFilter>("all");
  const headBtn = useRef<HTMLButtonElement>(null);
  const railBtn = useRef<HTMLButtonElement>(null);

  function toggle() {
    onToggle();
    // 토글 버튼이 숨겨지므로 반대편 버튼으로 포커스 이동 (접근성)
    requestAnimationFrame(() => (collapsed ? headBtn.current : railBtn.current)?.focus());
  }

  const isUnconfirmed = (f: Fact) => f.content.includes("(미확정");
  const shown = (facts ?? []).filter((f) =>
    filter === "all"
      ? true
      : filter === "active"
        ? f.status === "active" && !isUnconfirmed(f)
        : filter === "unconfirmed"
          ? f.status === "active" && isUnconfirmed(f)
          : f.status === "archived",
  );
  const statusOf = (f: Fact): "ok" | "warn" | "arch" =>
    f.status === "archived" ? "arch" : isUnconfirmed(f) ? "warn" : "ok";
  const STATUS_TEXT = { ok: "확립", warn: "미확정", arch: "아카이브" } as const;

  return (
    <aside className="fact-side" id="fact-side">
      <div className="fact-side-head">
        <h4>
          <Database aria-hidden="true" />
          팩트 저장소
        </h4>
        <div className="fact-side-head-tools">
          <span className="fact-count">{facts === null ? "…" : `${facts.length}건`}</span>
          <button
            type="button"
            ref={headBtn}
            className="fact-fold"
            onClick={toggle}
            aria-expanded={!collapsed}
            aria-controls="fact-side"
            aria-label="팩트 저장소 접기"
            title="팩트 저장소 접기"
          >
            <PanelRightClose aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className="fact-filter" role="tablist" aria-label="팩트 상태 필터">
        {FACT_FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            className={`fact-filter-btn ${filter === f.id ? "fact-filter-active" : ""}`}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && <Banner kind="error">{error}</Banner>}

      <div className="fact-side-list">
        {shown.length === 0 ? (
          <p className="hint">
            {filter === "all" ? "아직 팩트가 없습니다 — 인터뷰를 진행하면 적립됩니다." : "해당 상태의 팩트가 없습니다."}
          </p>
        ) : (
          shown.map((f) => {
            const st = statusOf(f);
            return (
              <div key={f.id} className="fact-card">
                <div className="fact-card-head">
                  <span className={`fact-chip fact-chip-${f.origin}`}>
                    {ORIGIN_LABEL[f.origin] ?? f.origin}
                  </span>
                  <span className={`fact-status fact-status-${st}`}>{STATUS_TEXT[st]}</span>
                </div>
                <p className="fact-card-body">{f.content}</p>
                <div className="fact-meta">
                  {f.source ? <span className="fact-src">출처: {f.source}</span> : <span className="fact-src">출처 없음</span>}
                  <span className="spacer" />
                  <span>{f.date}</span>
                </div>
              </div>
            );
          })
        )}
      </div>

      <p className="fact-side-note">
        팩트 확정(승인·적립)은 인터뷰의 [팩트 확인] 단계에서만 수행됩니다 — 게이트 우회 기록은 허용되지 않습니다.
      </p>

      <div className="fact-rail">
        <button
          type="button"
          ref={railBtn}
          className="fact-rail-btn"
          onClick={toggle}
          aria-expanded={!collapsed}
          aria-controls="fact-side"
          aria-label="팩트 저장소 펼치기"
          title="팩트 저장소 펼치기"
        >
          <PanelRightOpen aria-hidden="true" />
        </button>
        <span className="fact-rail-label" aria-hidden="true">
          팩트
        </span>
      </div>
    </aside>
  );
}