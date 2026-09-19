import { useCallback, useEffect, useRef, useState } from "react";
import {
  apiGet,
  apiPost,
  ApiError,
  type Job,
  type Plan,
  type Review,
  type ReviewFinding,
} from "../api/client";
import { Banner, Button, Empty, fmtDateTime } from "../components/ui";

const SEV_ICON: Record<string, string> = { red: "🔴", yellow: "🟡", white: "⚪" };
const SEV_ORDER: Record<string, number> = { red: 0, yellow: 1, white: 2 };

/** 검수 리포트 (FR-4, FR-5) — 결정론+LLM 발견사항 심각도 정렬 표시. 수정은 plan 탭 게이트로. */
export default function ReviewPanel({ pid }: { pid: number }) {
  const [reports, setReports] = useState<Review[] | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sel, setSel] = useState<Review | null>(null);
  const pollRef = useRef<number | null>(null);

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

  // 검수 잡 완료 감지 폴링 — OutputsPanel과 동일한 패턴
  useEffect(() => {
    const active = jobs.some((j) => j.type === "review" && (j.status === "queued" || j.status === "running"));
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

  return (
    <section>
      <div className="panel-head">
        <h3>검수</h3>
        <div className="panel-actions">
          {approvedPlan ? (
            <Button onClick={() => void enqueue()} disabled={busy}>
              검수 실행
            </Button>
          ) : (
            <span className="hint">검수에는 승인된 plan이 필요합니다 (plan 탭).</span>
          )}
        </div>
      </div>

      {error && <Banner kind="error">{error}</Banner>}
      {notice && <Banner kind="info">{notice}</Banner>}
      {busy && <Banner kind="info">검수 처리 중… (결정론 대조 + LLM 내용 검수)</Banner>}

      {reports.length === 0 ? (
        <Empty>아직 검수 리포트가 없습니다 — 산출물 생성 후 검수를 실행하세요.</Empty>
      ) : (
        <div className="card">
          <ul className="review-list">
            {reports.map((r) => (
              <li key={r.id} className={`review-row ${sel?.id === r.id ? "review-row-active" : ""}`}>
                <button className="review-open" onClick={() => setSel(r)}>
                  <span className="review-title">
                    검수 #{r.id} · plan v{r.plan_id}{" "}
                    {r.red_count > 0 ? (
                      <span className="sev sev-red">🔴 {r.red_count}</span>
                    ) : (
                      <span className="sev sev-clean">통과</span>
                    )}
                    {r.yellow_count > 0 && <span className="sev">🟡 {r.yellow_count}</span>}
                    {r.white_count > 0 && <span className="sev">⚪ {r.white_count}</span>}
                    {!r.llm_ok && <span className="sev sev-llm">LLM 검수 실패</span>}
                  </span>
                  <span className="hint">{fmtDateTime(r.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {sel && <ReviewDetail r={sel} />}
    </section>
  );
}

function ReviewDetail({ r }: { r: Review }) {
  const findings = (r.findings as ReviewFinding[])
    .slice()
    .sort((a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9));
  return (
    <div className="card">
      <div className="panel-head">
        <h4>
          발견사항 — 검수 #{r.id} (🔴 {r.red_count} · 🟡 {r.yellow_count} · ⚪ {r.white_count})
        </h4>
      </div>
      {r.summary && <p className="review-summary">{r.summary}</p>}
      {findings.length === 0 ? (
        <Empty>발견사항이 없습니다 — 결정론 대조와 LLM 내용 검수를 모두 통과했습니다.</Empty>
      ) : (
        <ul className="finding-list">
          {findings.map((f, i) => (
            <li key={i} className={`finding finding-${f.severity}`}>
              <span className="finding-sev">{SEV_ICON[f.severity] ?? f.severity}</span>
              <span className="finding-body">
                <span className="finding-where">
                  {f.where} <code>{f.code}</code>
                </span>
                <span className="finding-msg">{f.message}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="hint">
        🔴는 재생성 전 필수 수정 대상입니다. 수정은 plan 탭에서 plan을 고친 뒤 승인하고
        산출물을 재생성하세요 (FR-4.3 — SSOT 게이트 재사용).
      </p>
    </div>
  );
}