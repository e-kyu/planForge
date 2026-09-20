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
            type={props.type ?? "button"}>
      {props.children}
    </button>
  );
}

export function Banner(props: { kind?: "error" | "info" | "ok"; children: ReactNode }) {
  return (
    <div className={`banner banner-${props.kind ?? "info"}`} role="status">
      {props.children}
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

export function fmtDateTime(iso: string | unknown): string {
  if (typeof iso !== "string") return "";
  return iso.replace("T", " ").slice(0, 16);
}