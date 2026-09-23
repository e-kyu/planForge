import { useRef, useState } from "react";
import { FileCode, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Banner, Button, Empty, Loading } from "../../../shared/components/ui";
import { useStoredBoolean } from "../../../shared/lib/viewPrefs";
import { CmDiff, CmEditor } from "../../../shared/components/CmEditor";
import { MarkdownPreview } from "../../../shared/components/MarkdownPreview";
import { usePlans } from "../viewmodels/usePlans";

const STATUS_LABEL: Record<string, string> = {
  draft: "초안",
  approved: "승인됨",
  superseded: "이전 세대",
};

/** 표시 방식 세그먼트 토글 — 보기·대비 = 코드|뷰어, 편집 = 코드|분할|뷰어 (3모드 동일 UI). */
function SegToggle<T extends string>(props: {
  value: T;
  options: readonly { key: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="plan-seg" role="group" aria-label="표시 방식">
      {props.options.map((o) => (
        <button
          key={o.key}
          type="button"
          className={`plan-seg-btn ${props.value === o.key ? "plan-seg-active" : ""}`}
          onClick={() => props.onChange(o.key)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

type Mode = "view" | "edit" | "diff";
type ViewStyle = "code" | "viewer";
type EditStyle = "code" | "split" | "viewer";

/** plan.md 뷰어/에디터/승인 (FR-5, FR-2.9, FR-4.3).
 *  SSOT: 콘텐츠 원본은 DB plans.markdown — UI 수정은 항상 revise(새 세대 DRAFT)로만 간다. */
export default function PlanPanel({ pid }: { pid: number }) {
  const { plans, error, notice, setNotice, busy, approve, revise } = usePlans(pid);
  const [selId, setSelId] = useState<number | null>(null);
  const [mode, setMode] = useState<Mode>("view");
  const [viewStyle, setViewStyle] = useState<ViewStyle>("viewer"); // 표시 방식 (보기·대비 공유, 뷰어 기본)
  const [draft, setDraft] = useState<string | null>(null); // 편집 중 문서
  const [editStyle, setEditStyle] = useState<EditStyle>("code"); // 편집 표시 방식 (코드 기본)
  const [planCollapsed, setPlanCollapsed] = useStoredBoolean("pf-plan-side-collapsed", false);
  const headBtn = useRef<HTMLButtonElement>(null);
  const railBtn = useRef<HTMLButtonElement>(null);

  function toggle() {
    setPlanCollapsed(!planCollapsed);
    // 토글 버튼이 숨겨지므로 반대편 버튼으로 포커스 이동 (접근성)
    requestAnimationFrame(() => (planCollapsed ? headBtn.current : railBtn.current)?.focus());
  }

  if (plans === null) return <Loading />;
  if (plans.length === 0) {
    return <Empty>아직 plan이 없습니다 — 인터뷰를 완료하면 plan.md 초안이 여기에 나타납니다.</Empty>;
  }

  const sel = plans.find((p) => p.id === selId) ?? plans[plans.length - 1]!;
  const before = plans
    .filter((p) => p.version_no < sel.version_no)
    .sort((a, b) => b.version_no - a.version_no)[0];

  async function onApprove() {
    const id = await approve(sel.id);
    if (id !== null) {
      setSelId(id);
      setMode("view");
    }
  }

  async function onRevise() {
    if (draft === null) return;
    const id = await revise(sel.id, draft);
    if (id !== null) {
      setSelId(id);
      setMode("view");
      setDraft(null);
    }
  }

  const vlabel = (n: number) => `v${String(n).padStart(2, "0")}`;

  return (
    <section className={`plan-layout ${planCollapsed ? "plan-collapsed" : ""}`}>
      <aside className="plan-side" id="plan-side">
        <div className="plan-side-head">
          <h3>plan 세대 (DB Plan — SSOT)</h3>
          <button
            type="button"
            ref={headBtn}
            className="plan-fold"
            onClick={toggle}
            aria-expanded={!planCollapsed}
            aria-controls="plan-side"
            aria-label="plan 세대 접기"
            title="plan 세대 접기"
          >
            <PanelLeftClose aria-hidden="true" />
          </button>
        </div>
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

        <div className="plan-rail">
          <button
            type="button"
            ref={railBtn}
            className="plan-rail-btn"
            onClick={toggle}
            aria-expanded={!planCollapsed}
            aria-controls="plan-side"
            aria-label="plan 세대 펼치기"
            title="plan 세대 펼치기"
          >
            <PanelLeftOpen aria-hidden="true" />
          </button>
          <span className="plan-rail-label" aria-hidden="true">
            플랜
          </span>
        </div>
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
                setDraft(sel.markdown);
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
              {before ? `이전 세대 대비 (${vlabel(before.version_no)} → ${vlabel(sel.version_no)})` : "diff (이전 세대 없음)"}
            </Button>
            {mode === "edit" ? (
              <SegToggle
                value={editStyle}
                onChange={setEditStyle}
                options={[
                  { key: "code", label: "코드" },
                  { key: "split", label: "분할" },
                  { key: "viewer", label: "뷰어" },
                ]}
              />
            ) : (
              <SegToggle
                value={viewStyle}
                onChange={setViewStyle}
                options={[
                  { key: "code", label: "코드" },
                  { key: "viewer", label: "뷰어" },
                ]}
              />
            )}
          </div>
          <div className="plan-toolbar-right">
            {mode === "edit" && (
              <>
                <Button onClick={() => void onRevise()} disabled={busy || draft === sel.markdown}>
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
            {mode === "view" && sel.status === "draft" && (
              <Button variant="ok" onClick={() => void onApprove()} disabled={busy}>
                승인 (파생 단계 진입)
              </Button>
            )}
          </div>
        </div>

        <div className="plan-body">
          {mode === "edit" && draft !== null && editStyle === "code" && (
            <div className="cm-scroll">
              <CmEditor value={draft} onDocChange={setDraft} />
            </div>
          )}
          {mode === "edit" && draft !== null && editStyle === "split" && (
            <div className="plan-editor-split">
              <div className="cm-scroll">
                <CmEditor value={draft} onDocChange={setDraft} />
              </div>
              <div className="cm-scroll">
                <MarkdownPreview markdown={draft} />
              </div>
            </div>
          )}
          {mode === "edit" && draft !== null && editStyle === "viewer" && (
            <MarkdownPreview markdown={draft} />
          )}
          {mode === "diff" && before && viewStyle === "viewer" && (
            <div className="plan-viewer-split">
              <div className="plan-viewer-col">
                <div className="plan-viewer-head">{vlabel(before.version_no)} (이전 세대)</div>
                <MarkdownPreview markdown={before.markdown} />
              </div>
              <div className="plan-viewer-col">
                <div className="plan-viewer-head">{vlabel(sel.version_no)} (현재)</div>
                <MarkdownPreview markdown={sel.markdown} />
              </div>
            </div>
          )}
          {mode === "diff" && before && viewStyle === "code" && (
            <div className="cm-scroll">
              <CmDiff before={before.markdown} after={sel.markdown} />
            </div>
          )}
          {mode === "view" && viewStyle === "viewer" && (
            <MarkdownPreview markdown={sel.markdown} />
          )}
          {mode === "view" && viewStyle === "code" && (
            <div className="cm-scroll">
              <CmEditor value={sel.markdown} readOnly />
            </div>
          )}
        </div>
      </div>
    </section>
  );
}