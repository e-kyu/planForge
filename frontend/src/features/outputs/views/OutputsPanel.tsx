import { useState } from "react";
import { Download, Layout } from "lucide-react";
import type { Build, Job } from "../../../api/client";
import { Banner, Button, Empty, Loading, PageHeader, fmtBytes, fmtDateTime } from "../../../shared/components/ui";
import { JobErrorDetail } from "../../../shared/components/JobErrorDetail";
import { MarkdownPreview } from "../../../shared/components/MarkdownPreview";
import { useOutputs } from "../viewmodels/useOutputs";
import type { DocSlug } from "../../projects/models/docloops";
import { navigate } from "../../../shared/lib/hashRoute";
import { elapsedText, jobStateText, progressText, JOB_TYPE_LABEL } from "../../../shared/lib/jobs";
import type { DeriveFinding } from "../../../shared/lib/jobs";
import { JOB_STATUS_LABEL } from "../../../shared/lib/labels";
import { latestApproved } from "../../../shared/lib/plans";
import { jobsLoadErrorText } from "../../../shared/lib/messages";
import { formatVersion } from "../../../shared/lib/format";

const EXT_LABEL: Record<string, string> = {
  pptx: "PPTX",
  md: "MD",
  html: "HTML",
  docx: "DOCX",
};

type JobCounts = { slides?: number; sections?: number; attempts?: number };

/** 산출물 갤러리 (FR-3.4/3.5, FR-5) — 확장자별 버전, 미리보기(md/html 인라인, pptx/docx 다운로드).
 *  doc: 문서 루프 슬러그(레거시 라우트는 null) — 목록 조회 스코프(?doc_slug=)는 viewmodel 경유. */
export default function OutputsPanel({ pid, doc = null }: { pid: number; doc?: DocSlug | null }) {
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
  } = useOutputs(pid, doc);
  // docLabelSel: plan 본문 `- 산출 문서:` 라인의 한글 유형 라벨(생성 body.doc) —
  // prop doc(문서 루프 슬러그, body.doc_slug)과는 다른 개념이다 (viewmodel이 doc_slug를 채운다).
  const [docLabelSel, setDocLabelSel] = useState<string>("");
  // 배너 dismiss — 닫은 job id를 기억해 새 실패가 오면 배너가 다시 나타난다
  const [failedDismissId, setFailedDismissId] = useState<number | null>(null);
  const [residualDismissId, setResidualDismissId] = useState<number | null>(null);

  if (builds === null) return <Loading />;

  const approvedPlan = latestApproved(plans);
  const docs = (approvedPlan?.docs ?? []) as string[];
  // 대상 문서 미선택 해석 — 다중 문서 plan에서만 셀렉트가 보이므로 거기서는 실제 문서 선택을
  // 요구하고 생성 버튼을 잠근다 (단일 문서는 백엔드가 plan.docs[0]로 해석 — derive_build.py).
  const docRequired = docs.length > 1 && !docLabelSel;
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
        title="산출물 (자동 빌드)"
        desc="승인된 plan(SSOT)에서 Python 빌더가 자동으로 생성합니다. 버전 번호 규칙: 문서제목_vNN.확장자 — 같은 파일을 절대 덮어쓰지 않습니다."
      >
        {approvedPlan ? (
          <>
            {docs.length > 1 && (
              <select className="doc-select" aria-label="대상 문서" value={docLabelSel} onChange={(e) => setDocLabelSel(e.target.value)}>
                <option value="" disabled>
                  문서 유형을 선택하세요
                </option>
                {docs.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            )}
            <Button onClick={() => enqueue("slides", docLabelSel || undefined)} disabled={docRequired || busy}>
              PPT 생성 (슬라이드)
            </Button>
            <Button onClick={() => enqueue("report", docLabelSel || undefined, ["md"])} disabled={docRequired || busy}>
              MD 생성
            </Button>
            <Button onClick={() => enqueue("report", docLabelSel || undefined, ["html"])} disabled={docRequired || busy}>
              HTML 생성
            </Button>
            <Button onClick={() => enqueue("report", docLabelSel || undefined, ["docx"])} disabled={docRequired || busy}>
              DOCX 생성
            </Button>
          </>
        ) : (
          <span className="hint">산출물 생성에는 승인된 plan이 필요합니다 (plan 탭).</span>
        )}
      </PageHeader>

      <OutputBanners jobsError={jobsError} error={error} notice={notice} />
      {/* 상태창 — 워커가 기록한 진행 단계(reported by facade.report_progress)를 잡 폴링으로 표시.
          진행 문구·경과는 useTickingNow 틱으로 매초 갱신 — 폴링만으론 동일 페이로드에서 리렌더가 없다 */}
      {busy && <Banner kind="info">{busyBannerText(activeJob, now)}</Banner>}

      {residual && (
        <Banner kind="info" onDismiss={() => setResidualDismissId(residual.id)}>
          {/* 수치 위반이 남은 채 생성 완료 — 실패가 아니라 검수 자동 큐잉 (결정 17).
              최신 클린 생성이 이 배너를 대체한다 (latestDoneDeriveWithReds 규약). */}
          생성 완료 — 수치 검증에서 문제 {residual.total}건 (🔴 {residual.reds}건) — 검수가
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
          <span className="hint">버전 번호 규칙: 문서제목_vNN.확장자 — 같은 파일을 절대 덮어쓰지 않습니다</span>
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
                    {b.doc_kind} {EXT_LABEL[b.ext] ?? b.ext} {formatVersion(b.version_no)}
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
              미리보기 — {sel.doc_kind} {EXT_LABEL[sel.ext]} {formatVersion(sel.version_no)}
            </h4>
            <Button variant="ghost" onClick={closePreview}>
              닫기
            </Button>
          </div>
          <PreviewBody pid={pid} sel={sel} selPreview={selPreview} />
        </div>
      )}

      {recentJobs.length > 0 && (
        <div className="card">
          <div className="panel-head">
            <h4>작업 큐 (최근 5건)</h4>
          </div>
          <ul className="job-list">
            {recentJobs.map((j) => {
              const st = JOB_STATUS_LABEL[j.status];
              return (
                <li key={j.id} className={`job-item job-${j.status}`}>
                  <div className="job-head">
                    <span className="job-time">{fmtDateTime(j.created_at)}</span>
                    <span className={`badge badge-job-${j.status}`}>
                      {st?.icon} {st?.label ?? j.status}
                    </span>
                    <span className="job-title">{JOB_TYPE_LABEL[j.type] ?? j.type} #{j.id}</span>
                  </div>
                  <JobStatusDetail j={j} now={now} />
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}

/** 작업 상세줄 — 실패는 JobErrorDetail 공용 컴포넌트가 담당, 타입별 결과 요약
 * (result 스키마는 worker.py 참조). */
function JobStatusDetail({ j, now }: { j: Job; now: number }) {
  if (j.status === "running") {
    return (
      <div className="job-detail job-progress">
        {progressText(j) ?? "처리 중"}
        {elapsedText(j, now) ? ` · ${elapsedText(j, now)}` : ""}
      </div>
    );
  }
  if (j.status === "failed") return <JobErrorDetail job={j} />;
  return <div className="job-detail">{jobDetail(j)}</div>;
}

/** 상단 배너 묶음 — jobs 조회 실패·액션 오류·안내 (렌더 순서 유지). */
function OutputBanners(props: { jobsError: string | null; error: string | null; notice: string | null }) {
  return (
    <>
      {props.jobsError && <Banner kind="error">{jobsLoadErrorText(props.jobsError)}</Banner>}
      {props.error && <Banner kind="error">{props.error}</Banner>}
      {props.notice && <Banner kind="info">{props.notice}</Banner>}
    </>
  );
}

/** 진행 상태창 문구 — running은 job 진행+경과, 그 외(queued)는 큐 직렬 대기 안내. */
function busyBannerText(job: Job | undefined, now: number): string {
  if (job?.status === "running") return jobStateText(job, now) ?? "산출물 생성 — 처리 중";
  return "작업 대기 중 — 앞의 작업이 끝나면 시작됩니다 (한 번에 하나씩 처리)";
}

/** 미리보기 본문 — md는 마크다운, html은 iframe. */
function PreviewBody({ pid, sel, selPreview }: { pid: number; sel: Build; selPreview: string | null }) {
  if (sel.ext !== "md") {
    return <iframe className="html-preview" src={`/api/projects/${pid}/outputs/${sel.id}/download`} />;
  }
  if (!selPreview) return <Empty>미리보기 로딩 중…</Empty>;
  return <MarkdownPreview markdown={selPreview} />;
}

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