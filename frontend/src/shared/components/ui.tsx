import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

/** 공통 UI 조각 — 자체 CSS(§3.1). 라이브러리는 최소만 유지 (아이콘 lucide-react 허용). */

export function Button(props: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "ghost" | "danger" | "ok";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
  title?: string;
}) {
  const cls =
    props.variant === "ghost"
      ? "btn btn-ghost"
      : props.variant === "danger"
        ? "btn btn-danger"
        : props.variant === "ok"
          ? "btn btn-ok"
          : "btn btn-primary";
  return (
    <button className={`${cls} ${props.className ?? ""}`} onClick={props.onClick} disabled={props.disabled}
            type={props.type ?? "button"} title={props.title}>
      {props.children}
    </button>
  );
}

export function Banner(props: {
  kind?: "error" | "info" | "ok";
  children: ReactNode;
  onDismiss?: () => void;
}) {
  return (
    <div
      className={`banner banner-${props.kind ?? "info"} ${props.onDismiss ? "banner-dismiss" : ""}`}
      role="status"
    >
      {props.children}
      {props.onDismiss && (
        <button type="button" className="banner-close" aria-label="배너 닫기" onClick={props.onDismiss}>
          ×
        </button>
      )}
    </div>
  );
}

export function Loading(props: { label?: string }) {
  return <div className="loading">{props.label ?? "불러오는 중…"}</div>;
}

export function Empty(props: { children: ReactNode }) {
  return <div className="empty">{props.children}</div>;
}

/** 페이지헤더 카드 — 목업의 page-header (아이콘+제목+설명 좌측, 액션 우측). */
export function PageHeader(props: {
  icon: LucideIcon;
  title: string;
  desc?: string;
  children?: ReactNode;
}) {
  const Icon = props.icon;
  return (
    <div className="page-head">
      <div className="page-head-text">
        <h2>
          <Icon aria-hidden="true" />
          {props.title}
        </h2>
        {props.desc && <p>{props.desc}</p>}
      </div>
      {props.children && <div className="page-head-actions">{props.children}</div>}
    </div>
  );
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** UTC ISO(+00:00) → 로컬 "YYYY-MM-DD HH:mm". 백엔드 UTCDateTime 계약상 +00:00이 실려온다
 * (backend/app/shared/types.py). 기존 `slice(0,16)`은 UTC를 그대로 잘라 허상의 현지시각
 * (한국 저녁 잡이 한낮으로 보임)을 만들었으므로 변환한다 — job #34 사후 대응. 오프셋 없는
 * naive 문자열은 파싱 불가·미래 시각 부정확성을 피해 기존 동작을 유지한다(호환 폴백). */
export function fmtDateTime(iso: string | unknown): string {
  if (typeof iso !== "string") return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.replace("T", " ").slice(0, 16);
  const p = (n: number): string => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** 로컬 날짜 ("YYYY-MM-DD") — 프로젝트 생성일 등 date-only 표기 공용화.
 * (기존 `.slice(0, 10)`은 UTC 날짜를 잘라 한국 저녁 생성 프로젝트가 전날로 표기되는
 * fmtDateTime과 같은 분류의 결함.) */
export function fmtDate(iso: string | unknown): string {
  return fmtDateTime(iso).slice(0, 10);
}