import { useCallback, useEffect, useRef, useState } from "react";
import {
  apiGet,
  apiPost,
  ApiError,
  type Build,
  type Job,
  type Plan,
} from "../api/client";
import { Banner, Button, Empty, fmtBytes, fmtDateTime } from "../components/ui";
import { MarkdownPreview } from "../components/MarkdownPreview";

const EXT_LABEL: Record<string, string> = {
  pptx: "PPTX",
  md: "MD",
  html: "HTML",
  docx: "DOCX",
};

type JobCounts = { slides?: number; sections?: number; attempts?: number };

/** 산출물 갤러리 (FR-3.4/3.5, FR-5) — 확장자별 버전, 미리보기(md/html 인라인, pptx/docx 다운로드). */
export default function OutputsPanel({ pid }: { pid: number }) {
  const [builds, setBuilds] = useState<Build[] | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sel, setSel] = useState<Build | null>(null);
  const [selPreview, setSelPreview] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const [bs, ps, js] = await Promise.all([
        apiGet<Build[]>(`/api/projects/${pid}/outputs`),
        apiGet<Plan[]>(`/api/projects/${pid}/plans`),
        apiGet<Job[]>(`/api/projects/${pid}/jobs`),
      ]);
      setBuilds(bs);
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

  // 활성 job이 있으면 폴링 — 완료(queued/running 소멸) 시 갤러리 갱신
  useEffect(() => {
    const active = jobs.some((j) => j.status === "queued" || j.status === "running");
    if (!active) {
      // 완료 경로는 cleanup이 먼저 돌아 pollRef를 null로 만들므로, busy 해제는
      // pollRef 조건 없이 항상 실행해야 한다 — 조건부였더니 job 완료 후 busy가
      // true로 고착되어 생성 버튼이 영구 disabled 되는 버그 (e2e 5단계 사망 원인).
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

  async function enqueue(kind: "slides" | "report", doc: string | undefined, fmts?: string[]) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const job = await apiPost<Job>(`/api/projects/${pid}/derivatives`, {
        kind,
        doc,
        fmts,
      });
      setNotice(`작업 큐 진입 (#${job.id}) — 워커가 직렬 처리합니다.`);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  }

  const approvedPlan = [...plans].reverse().find((p) => p.status === "approved");
  const docs = (approvedPlan?.docs ?? []) as string[];
  const [docSel, setDocSel] = useState<string>("");

  async function preview(b: Build) {
    setSel(b);
    setSelPreview(null);
    if (b.ext === "md") {
      try {
        const res = await fetch(`/api/projects/${pid}/outputs/${b.id}/download`);
        setSelPreview(await res.text());
      } catch {
        setSelPreview("(미리보기를 읽지 못했습니다)");
      }
    }
  }

  if (builds === null) return <Empty>불러오는 중…</Empty>;

  const failedJobs = jobs.filter((j) => j.status === "failed");
  const recentJobs = [...jobs].reverse().slice(0, 5);

  return (
    <section>
      <div className="panel-head">
        <h3>산출물</h3>
        <div className="panel-actions">
          {approvedPlan ? (
            <>
              {docs.length > 1 && (
                <select aria-label="대상 문서" value={docSel} onChange={(e) => setDocSel(e.target.value)}>
                  <option value="">전체 문서(plan 첫 문서)</option>
                  {docs.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              )}
              <Button onClick={() => void enqueue("slides", docSel || undefined)} disabled={busy}>
                PPT 생성 (슬라이드)
              </Button>
              <Button onClick={() => void enqueue("report", docSel || undefined)} disabled={busy}>
                문서 생성 (MD·HTML·DOCX)
              </Button>
            </>
          ) : (
            <span className="hint">파생물 생성에는 승인된 plan이 필요합니다 (plan 탭).</span>
          )}
        </div>
      </div>

      {error && <Banner kind="error">{error}</Banner>}
      {notice && <Banner kind="info">{notice}</Banner>}
      {busy && <Banner kind="info">빌드 처리 중… (큐 직렬 처리)</Banner>}

      {failedJobs.length > 0 && (
        <Banner kind="error">
          실패한 작업 {failedJobs.length}건 —{" "}
          {failedJobs[failedJobs.length - 1]!.error_class === "validation" ||
          failedJobs[failedJobs.length - 1]!.error_class === "schema"
            ? "스키마/포맷 문제"
            : failedJobs[failedJobs.length - 1]!.error_class === "llm"
              ? "LLM 변환 문제"
              : failedJobs[failedJobs.length - 1]!.error_class === "builder"
                ? "빌더 문제"
                : "내부 오류"}
          : {failedJobs[failedJobs.length - 1]!.error?.split("\n")[0] ?? ""}
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
                    {b.doc_kind} {EXT_LABEL[b.ext] ?? b.ext} {fmtVersion(b.version_no)}
                  </span>
                  <span className="hint">
                    {fmtBytes(b.size_bytes)} · {fmtDateTime(b.created_at)} · plan v{b.plan_id}
                  </span>
                </button>
                <a className="btn btn-ghost" href={`/api/projects/${pid}/outputs/${b.id}/download`}>
                  {b.ext === "pptx" || b.ext === "docx" ? "다운로드" : "열기"}
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
            <Button variant="ghost" onClick={() => setSel(null)}>
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
            <h4>작업 큐 (최근)</h4>
          </div>
          <ul className="job-list">
            {recentJobs.map((j) => (
              <li key={j.id}>
                <span className={`badge badge-job-${j.status}`}>{j.status}</span>
                <span className="job-meta">
                  #{j.id} {j.type} · 파생물 {(j.payload as { kind?: string }).kind ?? "-"}
                  {(() => {
                    const c = j.result?.counts as JobCounts | undefined;
                    return c ? ` · 슬라이드 ${c.slides ?? "-"}/섹션 ${c.sections ?? "-"}` : "";
                  })()}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function fmtVersion(n: number): string {
  return `v${String(n).padStart(2, "0")}`;
}