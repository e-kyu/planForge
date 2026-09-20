import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, ShieldCheck, XCircle, type LucideIcon } from "lucide-react";
import {
  apiGet,
  apiPost,
  ApiError,
  type Job,
  type Plan,
  type Review,
  type ReviewFinding,
} from "../api/client";
import { Banner, Button, Empty, PageHeader, fmtDateTime } from "../components/ui";
import { navigate } from "../lib/hashRoute";

const SEV_ICON: Record<string, LucideIcon> = { red: XCircle, yellow: AlertTriangle, white: Info };
const SEV_LABEL: Record<string, string> = { red: "필수", yellow: "권고", white: "선택" };
const SEV_ORDER: Record<string, number> = { red: 0, yellow: 1, white: 2 };

/** 검수 리포트 (FR-4, FR-5) — 결정론+LLM 발견사항 심각도 정렬 표시 + 선택 반영(FR-4.3). */
export default function ReviewPanel({ pid }: { pid: number }) {
  const [reports, setReports] = useState<Review[] | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sel, setSel] = useState<Review | null>(null);
  const [reviseDone, setReviseDone] = useState(false);
  const pollRef = useRef<number | null>(null);
  const reviseSeenRef = useRef<Set<number>>(new Set());

  const load = useCallback(async () => {
    try {
      const [rs, ps, js] = await Promise.all([
        apiGet<Review[]>(`/api/projects/${pid}/reviews`),
        apiGet<Plan[]>(`/api/projects/${pid}/plans`),
        apiGet<Job[]>(`/api/projects/${pid}/jobs`),
      ]);
      setReports(rs);
      setPlans(ps);
      setJobs(js);
      return js;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      return null;
    }
  }, [pid]);

  useEffect(() => {
    void load();
  }, [load]);

  // 반영(revise) 잡 완료/실패 1회 통지 — 검수 잡과 같은 폴링 사이클을 쓴다
  useEffect(() => {
    for (const j of jobs) {
      if (j.type !== "plan_revise" || reviseSeenRef.current.has(j.id)) continue;
      if (j.status === "done") {
        reviseSeenRef.current.add(j.id);
        const res = (j.result ?? {}) as { version_no?: number };
        setNotice(`plan v${res.version_no ?? "?"} 생성 (초안) — plan 탭에서 diff로 검토한 뒤 승인하세요.`);
        setError(null);
        setReviseDone(true);
      } else if (j.status === "failed") {
        reviseSeenRef.current.add(j.id);
        setError(`plan 반영 실패: ${(j.error ?? "원인 불명").split("\n")[0]}`);
      }
    }
  }, [jobs]);

  // 검수·반영 잡 완료 감지 폴링 — OutputsPanel과 동일한 패턴
  useEffect(() => {
    const active = jobs.some(
      (j) =>
        (j.type === "review" || j.type === "plan_revise") &&
        (j.status === "queued" || j.status === "running"),
    );
    if (!active) {
      // OutputsPanel과 동일 — busy 해제는 pollRef 조건 없이 항상 실행
      // (완료 경로는 cleanup이 pollRef를 null로 만들어 조건부면 busy가 고착된다).
      setBusy(false);
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
        void load().then(() => undefined);
      }
      return;
    }
    if (pollRef.current === null) {
      setBusy(true);
      pollRef.current = window.setInterval(() => void load(), 1500);
    }
    return () => {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [jobs, load]);

  async function enqueue() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const job = await apiPost<Job>(`/api/projects/${pid}/reviews`);
      setNotice(`검수 작업 큐 진입 (#${job.id}) — 워커가 결정론+LLM 검수를 실행합니다.`);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  }

  if (reports === null) return <Empty>불러오는 중…</Empty>;

  const approvedPlan = [...plans].reverse().find((p) => p.status === "approved");
  const verById = new Map(plans.map((p) => [p.id, p.version_no]));
  const reviseActive = jobs.some(
    (j) => j.type === "plan_revise" && (j.status === "queued" || j.status === "running"),
  );
  const reviewActive = jobs.some(
    (j) => j.type === "review" && (j.status === "queued" || j.status === "running"),
  );

  return (
    <section>
      <PageHeader
        icon={ShieldCheck}
        title="수치·내용 검수 (Review)"
        desc="원본 plan.md(SSOT)와 생성된 파생 산출물 간 수치 오기와 구조 손실을 결정론 대조하고, LLM이 내용 검수를 수행합니다."
      >
        {reviseDone && (
          <Button onClick={() => navigate(`/projects/${pid}/plan`)}>plan 탭으로 이동</Button>
        )}
        {approvedPlan ? (
          <Button onClick={() => void enqueue()} disabled={busy}>
            검수 실행
          </Button>
        ) : (
          <span className="hint">검수에는 승인된 plan이 필요합니다 (plan 탭).</span>
        )}
      </PageHeader>

      {error && <Banner kind="error">{error}</Banner>}
      {notice && <Banner kind="info">{notice}</Banner>}
      {busy && (
        <Banner kind="info">
          {reviseActive && !reviewActive
            ? "plan 반영 처리 중… (LLM plan 수정 + 포맷 검증)"
            : "검수 처리 중… (결정론 대조 + LLM 내용 검수)"}
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
                  </span>
                  <span className="hint">{fmtDateTime(r.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {sel && <ReviewDetail key={sel.id} r={sel} />}
    </section>
  );
}

function ReviewDetail({ r }: { r: Review }) {
  // 반영 API는 r.findings의 원본 인덱스를 받으므로 정렬 전에 인덱스를 붙인다
  const findings = (r.findings as ReviewFinding[])
    .map((f, idx) => ({ f, idx }))
    .sort((a, b) => (SEV_ORDER[a.f.severity] ?? 9) - (SEV_ORDER[b.f.severity] ?? 9));
  const [selected, setSelected] = useState<Set<number>>(
    () => new Set(findings.map((x) => x.idx)),
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function toggle(idx: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }

  async function apply() {
    setBusy(true);
    setErr(null);
    setNotice(null);
    try {
      const job = await apiPost<Job>(`/api/plans/${r.plan_id}/revise-from-review`, {
        review_id: r.id,
        finding_indices: [...selected].sort((a, b) => a - b),
      });
      setNotice(`plan 반영 작업 큐 진입 (#${job.id}) — 워커가 LLM plan 수정을 실행합니다.`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="panel-head">
        <h4>
          발견사항 — 검수 #{r.id} (🔴 {r.red_count} · 🟡 {r.yellow_count} · ⚪ {r.white_count})
        </h4>
        {findings.length > 0 && (
          <div className="panel-actions">
            <Button onClick={() => void apply()} disabled={busy || selected.size === 0}>
              선택 항목 plan에 반영 (새 세대)
            </Button>
          </div>
        )}
      </div>
      {err && <Banner kind="error">{err}</Banner>}
      {notice && <Banner kind="info">{notice}</Banner>}
      {r.summary && <p className="review-summary">{r.summary}</p>}
      {findings.length === 0 ? (
        <Empty>발견사항이 없습니다 — 결정론 대조와 LLM 내용 검수를 모두 통과했습니다.</Empty>
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
        반영하면 선택한 발견사항을 LLM이 plan에 고쳐 새 plan 세대(초안)를 만듭니다.
        plan 탭에서 diff로 검토한 뒤 승인해야 산출물이 재생성됩니다 (FR-4.3 — SSOT 게이트).
        🔴는 재생성 전 필수 수정 대상입니다.
      </p>
    </div>
  );
}