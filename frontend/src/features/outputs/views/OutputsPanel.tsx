import { useState } from "react";
import { Download, Layout } from "lucide-react";
import type { Job } from "../../../api/client";
import { Banner, Button, Empty, PageHeader, fmtBytes, fmtDateTime } from "../../../shared/components/ui";
import { JobErrorDetail } from "../../../shared/components/JobErrorDetail";
import { MarkdownPreview } from "../../../shared/components/MarkdownPreview";
import { useOutputs } from "../viewmodels/useOutputs";
import { navigate } from "../../../shared/lib/hashRoute";
import { elapsedText, jobStateText, progressText, JOB_TYPE_LABEL } from "../../../shared/lib/jobs";
import type { DeriveFinding } from "../../../shared/lib/jobs";

const EXT_LABEL: Record<string, string> = {
  pptx: "PPTX",
  md: "MD",
  html: "HTML",
  docx: "DOCX",
};

type JobCounts = { slides?: number; sections?: number; attempts?: number };

/** 잡 타입·상태 레이블 — 타입 레이블은 공용 셀렉터(jobs.ts)에서 import한다. */
const JOB_STATUS: Record<string, { icon: string; label: string }> = {
  queued: { icon: "○", label: "대기" },
  running: { icon: "⟳", label: "진행" },
  done: { icon: "✓", label: "완료" },
  failed: { icon: "✕", label: "실패" },
  cancelled: { icon: "−", label: "취소" },
};

/** 산출물 갤러리 (FR-3.4/3.5, FR-5) — 확장자별 버전, 미리보기(md/html 인라인, pptx/docx 다운로드). */
export default function OutputsPanel({ pid }: { pid: number }) {
  const {
    builds,
    plans,
    jobs,
    failedLatest,
    residualJob,
    activeJob,
    jobsError,
    now,
    error,
    notice,
    busy,
    enqueue,
    preview,
    sel,
    selPreview,
    closePreview,
  } = useOutputs(pid);
  const [docSel, setDocSel] = useState<string>("");
  // 배너 dismiss — 닫은 job id를 기억해 새 실패가 오면 배너가 다시 나타난다
  const [failedDismissId, setFailedDismissId] = useState<number | null>(null);
  const [residualDismissId, setResidualDismissId] = useState<number | null>(null);

  if (builds === null) return <Empty>불러오는 중…</Empty>;

  const approvedPlan = [...plans].reverse().find((p) => p.status === "approved");
  const docs = (approvedPlan?.docs ?? []) as string[];
  // 대상 문서 미선택 해석 — 다중 문서 plan에서만 셀렉트가 보이므로 거기서는 실제 문서 선택을
  // 요구하고 생성 버튼을 잠근다 (단일 문서는 백엔드가 plan.docs[0]로 해석 — derive_build.py).
  const docRequired = docs.length > 1 && !docSel;
  const visibleFailed = failedLatest.filter((j) => j.id !== failedDismissId);
  const recentJobs = [...jobs].reverse().slice(0, 5);
  // 수치 위반 잔여 배너 — job.result.findings의 측정값만 표현한다 (판정은 검수 단계, 결정 17)
  const residualFindings = (residualJob?.result?.findings ?? []) as DeriveFinding[];
  const residual = residualJob && residualDismissId !== residualJob.id
    ? {
        id: residualJob.id,
        total: residualFindings.length,
        reds: residualFindings.filter((f) => f.severity === "red").length,
      }
    : undefined;

  return (
    <section>
      <PageHeader
        icon={Layout}
        title="파생 산출물 (결정론 빌드)"
        desc="승인된 plan(SSOT)에서 Python 빌더가 결정론적으로 생성합니다. 채번 규칙: 문서제목_vNN.확장자 — 절대 덮어쓰지 않습니다 (원칙 5)."
      >
        {approvedPlan ? (
          <>
            {docs.length > 1 && (
              <select className="doc-select" aria-label="대상 문서" value={docSel} onChange={(e) => setDocSel(e.target.value)}>
                <option value="" disabled>
                  문서유형선택
                </option>
                {docs.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            )}
            <Button onClick={() => enqueue("slides", docSel || undefined)} disabled={docRequired || busy}>
              PPT 생성 (슬라이드)
            </Button>
            <Button onClick={() => enqueue("report", docSel || undefined, ["md"])} disabled={docRequired || busy}>
              MD 생성
            </Button>
            <Button onClick={() => enqueue("report", docSel || undefined, ["html"])} disabled={docRequired || busy}>
              HTML 생성
            </Button>
            <Button onClick={() => enqueue("report", docSel || undefined, ["docx"])} disabled={docRequired || busy}>
              DOCX 생성
            </Button>
          </>
        ) : (
          <span className="hint">파생물 생성에는 승인된 plan이 필요합니다 (plan 탭).</span>
        )}
      </PageHeader>

      {jobsError && <Banner kind="error">작업 상태 조회 실패: {jobsError}</Banner>}
      {error && <Banner kind="error">{error}</Banner>}
      {notice && <Banner kind="info">{notice}</Banner>}
      {/* 상태창 — 워커가 기록한 진행 단계(reported by facade.report_progress)를 잡 폴링으로 표시.
          진행 문구·경과는 useTickingNow 틱으로 매초 갱신 — 폴링만으론 동일 페이로드에서 리렌더가 없다 */}
      {busy && (
        <Banner kind="info">
          {activeJob?.status === "running"
            ? (jobStateText(activeJob, now) ?? "파생물 생성 — 처리 중")
            : "작업 대기 중 — 앞의 작업이 끝나면 시작됩니다 (큐 직렬 처리)"}
        </Banner>
      )}

      {residual && (
        <Banner kind="info" onDismiss={() => setResidualDismissId(residual.id)}>
          {/* 수치 위반이 남은 채 생성 완료 — 실패가 아니라 검수 자동 큐잉 (결정 17).
              최신 클린 생성이 이 배너를 대체한다 (latestDoneDeriveWithReds 규약). */}
          생성 완료 — 수치 무결성 미달 {residual.total}건 (🔴 {residual.reds}건) — 검수가
          자동 실행되어 대조합니다.
          <Button variant="ghost" onClick={() => navigate(`/projects/${pid}/review`)}>
            검수로 이동
          </Button>
        </Banner>
      )}

      {visibleFailed.length > 0 && (
        <Banner kind="error" onDismiss={() => setFailedDismissId(visibleFailed[visibleFailed.length - 1]!.id)}>
          {/* 저장된 오류 전문(job.error)에 실린 진단 목록을 잃지 않게 토글로 펼친다 (결정 16) */}
          <JobErrorDetail job={visibleFailed[visibleFailed.length - 1]!} title={`실패한 작업 ${visibleFailed.length}건`} />
        </Banner>
      )}

      <div className="card">
        <div className="panel-head">
          <h4>갤러리</h4>
          <span className="hint">채번 규칙: 문서제목_vNN.확장자 — 절대 덮어쓰지 않습니다 (원칙 5)</span>
        </div>
        {builds.length === 0 ? (
          <Empty>아직 산출물이 없습니다 — 승인된 plan으로 생성하세요.</Empty>
        ) : (
          <ul className="output-list">
            {builds.map((b) => (
              <li key={b.id} className={`output-row ${sel?.id === b.id ? "output-row-active" : ""}`}>
                <button className="output-open" onClick={() => void preview(b)}>
                  <span className="output-title">
                    <span className={`ext-chip ext-${b.ext}`}>{EXT_LABEL[b.ext] ?? b.ext}</span>
                    {b.doc_kind} {EXT_LABEL[b.ext] ?? b.ext} {fmtVersion(b.version_no)}
                  </span>
                  <span className="hint">
                    {fmtBytes(b.size_bytes)} · {fmtDateTime(b.created_at)} · plan v{b.plan_id}
                  </span>
                </button>
                {/* md/html은 열기(새 탭, inline) + 다운로드(download 속성) 2버튼, pptx/docx는 다운로드 1버튼 */}
                {(b.ext === "md" || b.ext === "html") && (
                  <a
                    className="btn btn-ghost"
                    href={`/api/projects/${pid}/outputs/${b.id}/download`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    열기
                  </a>
                )}
                <a
                  className="btn btn-ghost"
                  href={`/api/projects/${pid}/outputs/${b.id}/download`}
                  download
                >
                  <Download aria-hidden="true" />
                  다운로드
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>

      {sel && (sel.ext === "md" || sel.ext === "html") && (
        <div className="card">
          <div className="panel-head">
            <h4>
              미리보기 — {sel.doc_kind} {EXT_LABEL[sel.ext]} {fmtVersion(sel.version_no)}
            </h4>
            <Button variant="ghost" onClick={closePreview}>
              닫기
            </Button>
          </div>
          {sel.ext === "md" ? (
            selPreview ? (
              <MarkdownPreview markdown={selPreview} />
            ) : (
              <Empty>미리보기 로딩 중…</Empty>
            )
          ) : (
            <iframe className="html-preview" src={`/api/projects/${pid}/outputs/${sel.id}/download`} />
          )}
        </div>
      )}

      {recentJobs.length > 0 && (
        <div className="card">
          <div className="panel-head">
            <h4>작업 큐 (최근 5건)</h4>
          </div>
          <ul className="job-list">
            {recentJobs.map((j) => {
              const st = JOB_STATUS[j.status];
              return (
                <li key={j.id} className={`job-item job-${j.status}`}>
                  <div className="job-head">
                    <span className="job-time">{fmtDateTime(j.created_at)}</span>
                    <span className={`badge badge-job-${j.status}`}>
                      {st?.icon} {st?.label ?? j.status}
                    </span>
                    <span className="job-title">{JOB_TYPE_LABEL[j.type] ?? j.type} #{j.id}</span>
                  </div>
                  {j.status === "running" ? (
                    <div className="job-detail job-progress">
                      {progressText(j) ?? "처리 중"}
                      {elapsedText(j, now) ? ` · ${elapsedText(j, now)}` : ""}
                    </div>
                  ) : j.status === "failed" ? (
                    <JobErrorDetail job={j} />
                  ) : (
                    <div className="job-detail">{jobDetail(j)}</div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}

function fmtVersion(n: number): string {
  return `v${String(n).padStart(2, "0")}`;
}

/** 작업 상세줄 — 실패는 JobErrorDetail 공용 컴포넌트가 담당, 타입별 결과 요약
 * (result 스키마는 worker.py 참조). */
function jobDetail(j: Job): string {
  if (j.type === "review") {
    const c = j.result?.counts as { red?: number; yellow?: number; white?: number } | undefined;
    return c ? `🔴 ${c.red ?? 0} · 🟡 ${c.yellow ?? 0} · ⚪ ${c.white ?? 0}` : "결과 대기 중";
  }
  if (j.type === "plan_revise") {
    const r = j.result as { version_no?: number; applied_count?: number } | null;
    return r ? `plan v${r.version_no} 생성 (반영 ${r.applied_count ?? 0}건)` : "결과 대기 중";
  }
  const kind = (j.payload as { kind?: string }).kind ?? "-";
  const c = j.result?.counts as JobCounts | undefined;
  const base = c ? `${kind} · 슬라이드 ${c.slides ?? "-"}/섹션 ${c.sections ?? "-"}` : kind;
  // 수치 측정값 영속 기록 — 발견사항 수 요약 (판정은 검수 리포트가 담당 — 결정 17)
  const f = (j.result?.findings ?? null) as DeriveFinding[] | null;
  if (!f?.length) return base;
  return `${base} · 위반 ${f.length}건(🔴 ${f.filter((x) => x.severity === "red").length}건)`;
}