import { useEffect, useState } from "react";
import { FileCode } from "lucide-react";
import { apiGet, apiPost, ApiError, type Plan } from "../api/client";
import { Banner, Button, Empty, Loading } from "../components/ui";
import { CmDiff, CmEditor } from "../components/CmEditor";
import { MarkdownPreview } from "../components/MarkdownPreview";

const STATUS_LABEL: Record<string, string> = {
  draft: "초안",
  approved: "승인됨",
  superseded: "이전 세대",
};

type Mode = "view" | "edit" | "diff";

/** plan.md 뷰어/에디터/승인 (FR-5, FR-2.9, FR-4.3).
 *  SSOT: 콘텐츠 원본은 DB plans.markdown — UI 수정은 항상 revise(새 세대 DRAFT)로만 간다. */
export default function PlanPanel({ pid }: { pid: number }) {
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [selId, setSelId] = useState<number | null>(null);
  const [mode, setMode] = useState<Mode>("view");
  const [draft, setDraft] = useState<string | null>(null); // 편집 중 문서
  const [preview, setPreview] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load(selectId?: number | null) {
    try {
      const list = await apiGet<Plan[]>(`/api/projects/${pid}/plans`);
      setPlans(list);
      if (list.length > 0) {
        setSelId(selectId ?? list[list.length - 1]?.id ?? null);
      }
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }
  useEffect(() => {
    void load();
  }, [pid]);

  if (plans === null) return <Loading />;
  if (plans.length === 0) {
    return <Empty>아직 plan이 없습니다 — 인터뷰를 완료하면 plan.md 초안이 여기에 나타납니다.</Empty>;
  }

  const sel = plans.find((p) => p.id === selId) ?? plans[plans.length - 1]!;
  const before = plans
    .filter((p) => p.version_no < sel.version_no)
    .sort((a, b) => b.version_no - a.version_no)[0];

  async function approve() {
    if (!sel) return;
    setBusy(true);
    setError(null);
    try {
      const p = await apiPost<Plan>(`/api/plans/${sel.id}/approve`);
      setNotice(`plan v${String(p.version_no).padStart(2, "0")} 승인 — 산출물 탭에서 파생물을 생성하세요.`);
      await load(p.id);
      setMode("view");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function revise() {
    if (!sel || draft === null) return;
    setBusy(true);
    setError(null);
    try {
      const p = await apiPost<Plan>(`/api/plans/${sel.id}/revise`, { markdown: draft });
      setNotice(`plan v${String(p.version_no).padStart(2, "0")} 생성 (새 초안) — 승인해 주세요.`);
      await load(p.id);
      setMode("view");
      setDraft(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e)); // 포맷 검증 실패(422)도 여기
    } finally {
      setBusy(false);
    }
  }

  const vlabel = (n: number) => `v${String(n).padStart(2, "0")}`;

  return (
    <section className="plan-layout">
      <aside className="plan-side">
        <h3>plan 세대 (DB Plan — SSOT)</h3>
        <ul className="plan-list">
          {plans.map((p) => (
            <li key={p.id}>
              <button
                className={`plan-row ${p.id === selId ? "plan-row-active" : ""}`}
                onClick={() => {
                  setSelId(p.id);
                  setMode("view");
                  setDraft(null);
                  setNotice(null);
                }}
              >
                <span>{vlabel(p.version_no)}</span>
                <span className={`badge badge-plan-${p.status}`}>
                  {STATUS_LABEL[p.status] ?? p.status}
                </span>
                {(p.docs ?? []).length > 0 && (
                  <span className="plan-row-docs">[문서: {(p.docs ?? []).map(String).join("+")}]</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <div className="plan-main">
        {error && <Banner kind="error">{error}</Banner>}
        {notice && <Banner kind="ok">{notice}</Banner>}

        <div className="plan-toolbar">
          <div className="plan-toolbar-left">
            <span className="plan-caption">
              <FileCode aria-hidden="true" />
              plan.md (Single Source of Truth)
            </span>
            <Button
              variant="ghost"
              onClick={() => {
                setMode("view");
                setDraft(null);
              }}
              disabled={busy}
            >
              보기
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setDraft(sel!.markdown);
                setMode("edit");
                setNotice(null);
              }}
              disabled={busy}
            >
              편집
            </Button>
            <Button
              variant="ghost"
              disabled={busy || !before}
              onClick={() => setMode(before ? "diff" : "view")}
            >
              {before ? `이전 세대 대비 (${vlabel(before.version_no)} → ${vlabel(sel!.version_no)})` : "diff (이전 세대 없음)"}
            </Button>
          </div>
          <div className="plan-toolbar-right">
            {mode === "edit" && (
              <label className="chk">
                <input type="checkbox" checked={preview} onChange={(e) => setPreview(e.target.checked)} />
                미리보기
              </label>
            )}
            {mode === "edit" && sel && (
              <>
                <Button onClick={() => void revise()} disabled={busy || draft === sel.markdown}>
                  저장 (새 세대)
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => {
                    setMode("view");
                    setDraft(null);
                  }}
                  disabled={busy}
                >
                  취소
                </Button>
              </>
            )}
            {mode === "view" && sel?.status === "draft" && (
              <Button variant="ok" onClick={() => void approve()} disabled={busy}>
                승인 (파생 단계 진입)
              </Button>
            )}
          </div>
        </div>

        <div className="plan-body">
          {mode === "edit" && draft !== null && (
            <div className={`plan-editor ${preview ? "plan-editor-split" : ""}`}>
              <div className="cm-scroll">
                <CmEditor value={draft} onDocChange={setDraft} />
              </div>
              {preview && (
                <div className="cm-scroll">
                  <MarkdownPreview markdown={draft} />
                </div>
              )}
            </div>
          )}
          {mode === "diff" && before && (
            <div className="cm-scroll">
              <CmDiff before={before.markdown} after={sel!.markdown} />
            </div>
          )}
          {mode === "view" && sel && (
            <div className="cm-scroll">
              <CmEditor value={sel.markdown} readOnly />
            </div>
          )}
        </div>
      </div>
    </section>
  );
}