import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";

/** 공용 모달 — overlay/panel 마크업·role/aria-modal·닫기 버튼·overlay 클릭 닫기를 한 곳에 모은다.
 *  Esc 리스너도 여기가 소유한다 (DOM/UI 효과는 View 허용 — ADR 편차 4).
 *  closeDisabled: 작업 중 닫기 차단(기존 화면의 busy/delBusy 가드)을 그대로 유지하기 위한 옵션. */
export function Modal(props: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  labelledBy?: string;
  className?: string;
  closeDisabled?: boolean;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") props.onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [props.onClose]);

  return (
    <div className="modal-overlay" onClick={props.onClose}>
      <div
        className={props.className ? `modal ${props.className}` : "modal"}
        role="dialog"
        aria-modal="true"
        aria-labelledby={props.labelledBy}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h3 id={props.labelledBy}>{props.title}</h3>
          <button
            className="modal-close"
            onClick={props.onClose}
            disabled={props.closeDisabled}
            aria-label="닫기"
          >
            <X />
          </button>
        </div>
        {props.children}
      </div>
    </div>
  );
}
