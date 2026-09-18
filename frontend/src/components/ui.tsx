import type { ReactNode } from "react";

/** 공통 UI 조각 — 자체 CSS(§3.1). 라이브러리 도입 없이 최소만 유지한다. */

export function Button(props: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "ghost" | "danger";
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  const cls =
    props.variant === "ghost"
      ? "btn btn-ghost"
      : props.variant === "danger"
        ? "btn btn-danger"
        : "btn btn-primary";
  return (
    <button className={cls} onClick={props.onClick} disabled={props.disabled}
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

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function fmtDateTime(iso: string | unknown): string {
  if (typeof iso !== "string") return "";
  return iso.replace("T", " ").slice(0, 16);
}