import { useState } from "react";
import type { Job } from "../../api/client";
import { JOB_ERROR_CLASS_LABEL } from "../lib/jobs";

/** 실패한 job의 오류 요약 행 + "자세히" 토글 — DB에 저장된 전체 오류(job.error, Traceback
 * 포함)를 pre로 펼친다. 워커가 저장한 오류 본문은 진단 목록(여러 줄)을 담고 있으므로
 * 첫 줄만 노출하면 진단이 숨겨진다 — job #34 사후 대응(결정 16). OutputsPanel 실패 배너·
 * 잡 목록 행, ReviewPanel 반영 배너 공용. View 규칙 준수: fetch 없음(표현 전용), 로컬
 * 토글 상태만. */
export function JobErrorDetail({ job, title }: { job: Job; title?: string }) {
  const [open, setOpen] = useState(false);
  if (job.status !== "failed") return null;
  const err = job.error ?? "";
  const first = err.split("\n")[0] ?? "";
  const cls = job.error_class
    ? (JOB_ERROR_CLASS_LABEL[job.error_class] ?? "내부 오류")
    : "오류";
  const head = [title, cls, first].filter(Boolean).join(" — ");
  return (
    <div className="job-error">
      <div className="job-error-head">
        <span>{head}</span>
        {err && (
          <button
            type="button"
            className="job-error-toggle"
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            {open ? "간략히" : "자세히"}
          </button>
        )}
      </div>
      {open && err && <pre className="job-error-full">{err}</pre>}
    </div>
  );
}