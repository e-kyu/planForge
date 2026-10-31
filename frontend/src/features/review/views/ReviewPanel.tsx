import { useState } from "react";
import { AlertTriangle, CheckCircle2, Info, ShieldCheck, XCircle, type LucideIcon } from "lucide-react";
import type { Job, Review, ReviewFinding } from "../../../api/client";
import { Banner, Button, Empty, Loading, PageHeader, fmtDateTime } from "../../../shared/components/ui";
import { JobErrorDetail } from "../../../shared/components/JobErrorDetail";
import { navigate } from "../../../shared/lib/hashRoute";
import { elapsedText, isActive, latestByType, progressText } from "../../../shared/lib/jobs";
import { latestApproved } from "../../../shared/lib/plans";
import { jobsLoadErrorText } from "../../../shared/lib/messages";
import { useReviewApply, useReviews } from "../viewmodels/useReviews";

const SEV_ICON: Record<string, LucideIcon> = { red: XCircle, yellow: AlertTriangle, white: Info };
const SEV_LABEL: Record<string, string> = { red: "필수", yellow: "권고", white: "선택" };
const SEV_ORDER: Record<string, number> = { red: 0, yellow: 1, white: 2 };

/** 검수 리포트 (FR-4, FR-5) — 결정론+LLM 발견사항 심각도 정렬 표시 + 선택 반영(FR-4.3).
 *  문서 루프 프로젝트는 doc이 지정된 문서의 최신 승인 plan을 검수한다 (독립 진행). */
export default function ReviewPanel({ pid, doc = null }: { pid: number; doc?: string | null }) {
  const { reports, plans, jobs, jobsError, now, error, failedReviseJob, notice, busy, reviseDone, enqueue } =
    useReviews(pid, doc);
  const [sel, setSel] = useState<Review | null>(null);

  if (reports === null) return <Loading />;

  // 검수 대상 plan — 문서 컨텍스트가 있으면 그 문서의 승인 plan만 (독립 검수).
  const approvedPlan = latestApproved(plans, doc);
  const verById = new Map(plans.map((p) => [p.id, p.version_no]));
  // 배너 기준 잡 — 타입별 최신(마지막 상태) 잡. 진행 문구·경과를 잡 폴링에서 파생한다.
  const reviseJob = latestByType(jobs, "plan_revise");
  const reviewJob = latestByType(jobs, "review");
  const reviseActive = reviseJob !== undefined && isActive(reviseJob);
  const reviewActive = reviewJob !== undefined && isActive(reviewJob);

  return (
    <section>
      <PageHeader
        icon={ShieldCheck}
        title="수치·내용 검수 (Review)"
        desc="원본 plan.md(SSOT)와 생성된 산출물 간 수치 오기와 구조 손실을 자동으로 대조하고, LLM이 내용 검수를 수행합니다."
      >
        {reviseDone && (
          <Button onClick={() => navigate(`/projects/${pid}/plan`)}>plan 탭으로 이동</Button>
        )}
        {approvedPlan ? (
          <Button onClick={enqueue} disabled={busy}>
            검수 실행
          </Button>
        ) : (
          <span className="hint">검수에는 승인된 plan이 필요합니다 (plan 탭).</span>
        )}
      </PageHeader>

      <ReviewBanners
        jobsError={jobsError}
        error={error}
        failedReviseJob={failedReviseJob}
        notice={notice}
      />
      {busy && (
        <Banner kind="info">
          {busyBannerText(reviseActive, reviewActive, reviseJob, reviewJob, now)}
        </Banner>
      )}

      {reports.length === 0 ? (
        <Empty>아직 검수 리포트가 없습니다 — 산출물 생성 후 검수를 실행하세요.</Empty>
      ) : (
        <div className="card">
          <ul className="review-list">
            {reports.map((r) => (
              <li key={r.id} className={`review-row ${sel?.id === r.id ? "review-row-active" : ""}`}>
                <button className="review-open" onClick={() => setSel(r)}>
                  <span className="review-title">
                    검수 #{r.id} · plan v{verById.get(r.plan_id) ?? r.plan_id}{" "}
                    <ReviewSeverity r={r} />
                  </span>
                  <span className="hint">{fmtDateTime(r.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {sel && <ReviewDetail key={sel.id} r={sel} pid={pid} />}
    </section>
  );
}

/** 심각도 칩 — 🔴(없으면 "통과")·🟡·⚪·LLM 실패 (렌더 순서·문구 유지). */
function ReviewSeverity({ r }: { r: Review }) {
  return (
    <>
      {r.red_count > 0 ? (
        <span className="sev sev-red">
          <XCircle /> {r.red_count}
        </span>
      ) : (
        <span className="sev sev-clean">
          <CheckCircle2 /> 통과
        </span>
      )}
      {r.yellow_count > 0 && (
        <span className="sev sev-yellow">
          <AlertTriangle /> {r.yellow_count}
        </span>
      )}
      {r.white_count > 0 && (
        <span className="sev sev-white">
          <Info /> {r.white_count}
        </span>
      )}
      {!r.llm_ok && <span className="sev sev-llm">LLM 검수 실패</span>}
    </>
  );
}

/** 상단 배너 묶음 — jobs 조회 실패·액션 오류·plan 반영 실패·안내 (렌더 순서 유지). */
function ReviewBanners(props: {
  jobsError: string | null;
  error: string | null;
  failedReviseJob: Job | null | undefined;
  notice: string | null;
}) {
  return (
    <>
      {props.jobsError && <Banner kind="error">{jobsLoadErrorText(props.jobsError)}</Banner>}
      {props.error && <Banner kind="error">{props.error}</Banner>}
      {props.failedReviseJob && (
        <Banner kind="error">
          {/* 저장된 오류 전문에 실린 진단을 잃지 않게 토글로 펼친다 (결정 16) */}
          <JobErrorDetail job={props.failedReviseJob} title="plan 반영 실패" />
        </Banner>
      )}
      {props.notice && <Banner kind="info">{props.notice}</Banner>}
    </>
  );
}

/** 진행 배너 문구 — plan 반영만 활성이면 반영 안내, 그 외에는 검수 안내. */
function busyBannerText(
  reviseActive: boolean,
  reviewActive: boolean,
  reviseJob: Job | undefined,
  reviewJob: Job | undefined,
  now: number,
): string {
  if (reviseActive && !reviewActive) {
    return bannerText(reviseJob, now, "plan 반영 처리 중… (LLM plan 수정 + 포맷 검증)");
  }
  return bannerText(reviewJob, now, "검수 처리 중… (자동 대조 + LLM 내용 검수)");
}

/** 활성 잡의 진행 문구 + 경과 — 경과는 useTickingNow의 now로 갱신한다 (폴링만으론 정지).
 *  진행 기록이 없는 구간(결정론 대조 등)은 기존 안내 문구 유지. */
function bannerText(job: Job | undefined, now: number, fallback: string): string {
  if (!job) return fallback;
  if (job.status === "queued") return "작업 대기 중 — 앞의 작업이 끝나면 시작됩니다";
  const text = progressText(job, fallback);
  if (text === null) return fallback;
  const elapsed = elapsedText(job, now);
  return elapsed ? `${text} · ${elapsed}` : text;
}

function ReviewDetail({ r, pid }: { r: Review; pid: number }) {
  // 반영 API는 r.findings의 원본 인덱스를 받으므로 정렬 전에 인덱스를 붙인다
  const findings = (r.findings as ReviewFinding[])
    .map((f, idx) => ({ f, idx }))
    .sort((a, b) => (SEV_ORDER[a.f.severity] ?? 9) - (SEV_ORDER[b.f.severity] ?? 9));
  const { busy, err, notice, apply } = useReviewApply(r.plan_id, r.id, pid);
  const [selected, setSelected] = useState<Set<number>>(
    () => new Set(findings.map((x) => x.idx)),
  );

  function toggle(idx: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }

  return (
    <div className="card">
      <div className="panel-head">
        <h4>
          발견사항 — 검수 #{r.id} (🔴 {r.red_count} · 🟡 {r.yellow_count} · ⚪ {r.white_count})
        </h4>
        {findings.length > 0 && (
          <div className="panel-actions">
            <Button
              onClick={() => void apply([...selected].sort((a, b) => a - b))}
              disabled={busy || selected.size === 0}
            >
              선택한 항목을 plan에 반영 (새 버전 만들기)
            </Button>
          </div>
        )}
      </div>
      {err && <Banner kind="error">{err}</Banner>}
      {notice && <Banner kind="info">{notice}</Banner>}
      {r.summary && <p className="review-summary">{r.summary}</p>}
      {findings.length === 0 ? (
        <Empty>발견사항이 없습니다 — 자동 대조와 LLM 내용 검수를 모두 통과했습니다.</Empty>
      ) : (
        <ul className="finding-list">
          {findings.map(({ f, idx }) => {
            const SevIcon = SEV_ICON[f.severity];
            return (
              <li key={idx} className={`finding finding-${f.severity}`}>
                <input
                  type="checkbox"
                  className="finding-check"
                  aria-label="반영 대상 선택"
                  checked={selected.has(idx)}
                  onChange={() => toggle(idx)}
                />
                <span className={`sev sev-${f.severity}`}>
                  {SevIcon ? <SevIcon aria-hidden="true" /> : null}
                  {SEV_LABEL[f.severity] ?? f.severity}
                </span>
                <span className="finding-body">
                  <span className="finding-where">
                    {f.where} <code>{f.code}</code>
                  </span>
                  <span className="finding-msg">{f.message}</span>
                  {f.suggestion && <span className="finding-suggestion">↳ {f.suggestion}</span>}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      <p className="hint">
        반영하면 선택한 발견사항을 LLM이 plan에 수정 반영해 새 plan 버전(초안)을 만듭니다.
        plan 탭에서 diff로 검토한 뒤 승인해야 산출물이 재생성됩니다 — 원본은 plan 하나뿐이므로
        산출물을 직접 수정하는 대신 plan만 고칩니다. 🔴는 재생성 전 필수 수정 대상입니다.
      </p>
    </div>
  );
}