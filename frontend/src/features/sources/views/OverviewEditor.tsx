import { useState } from "react";
import { Download, FileCode, FileText } from "lucide-react";
import { Banner, Button, Loading, PageHeader } from "../../../shared/components/ui";
import { CmEditor } from "../../../shared/components/CmEditor";
import { MarkdownPreview } from "../../../shared/components/MarkdownPreview";
import { useOverviewEditor } from "../viewmodels/useOverview";

/** 표시 방식 세그먼트 토글 — PlanPanel의 SegToggle을 파일별 복제 (코드|분할|뷰어 3모드 동일 UI). */
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

type EditStyle = "code" | "split" | "viewer";

/** 개요 문서 편집기 (sources/overview.md) — 인터뷰 기본자료 전용 웹 작성 문서.
 *  파일이 곧 SSOT인 fs 네이티브 문서: 저장(PUT upsert)이 콘텐츠를 직접 기록하고,
 *  plan과 달리 세대·승인 개념이 없다. */
export default function OverviewEditor({ pid, onBack }: { pid: number; onBack: () => void }) {
  const { meta, loadError, draft, setDraft, error, notice, busy, dirty, save } =
    useOverviewEditor(pid);
  const [editStyle, setEditStyle] = useState<EditStyle>("code");

  function onCancel() {
    // 개요 문서는 이력(세대)이 없어 취소 = 영구 소실 — 변경이 있으면 1회 확인한다
    if (dirty && !window.confirm("저장하지 않은 변경 내용이 사라집니다 — 취소할까요?")) return;
    onBack();
  }

  if (meta === null || draft === null) {
    return loadError ? <Banner kind="error">{loadError}</Banner> : <Loading label="개요 문서 확인 중…" />;
  }

  const downloadHref = `/api/projects/${pid}/sources/overview.md/download`;

  return (
    <section>
      <PageHeader
        icon={FileText}
        title={meta.exists ? "개요 편집" : "개요 작성"}
        desc="sources/overview.md — 인터뷰 진행 시 기본자료로 주입되는 개요 문서. 결과물(plan·산출물) 생성에는 사용되지 않습니다."
      >
        {meta.exists && (
          <a className="btn btn-ghost" href={downloadHref} download>
            <Download aria-hidden="true" /> 다운로드
          </a>
        )}
        <Button variant="ghost" onClick={onBack}>
          목록으로
        </Button>
      </PageHeader>
      {error && <Banner kind="error">{error}</Banner>}
      {notice && <Banner kind="ok">{notice}</Banner>}

      <div className="card">
        <div className="plan-toolbar">
          <div className="plan-toolbar-left">
            <span className="plan-caption">
              <FileCode aria-hidden="true" />
              overview.md
            </span>
            <SegToggle
              value={editStyle}
              onChange={setEditStyle}
              options={[
                { key: "code", label: "코드" },
                { key: "split", label: "분할" },
                { key: "viewer", label: "뷰어" },
              ]}
            />
          </div>
          <div className="plan-toolbar-right">
            <Button
              onClick={save}
              disabled={busy || !dirty || !draft.trim()}
              title={!draft.trim() ? "빈 개요 문서는 저장할 수 없습니다" : undefined}
            >
              저장
            </Button>
            <Button variant="ghost" onClick={onCancel} disabled={busy}>
              취소
            </Button>
          </div>
        </div>

        <div className="plan-body">
          {editStyle === "code" && (
            <div className="cm-scroll">
              <CmEditor value={draft} onDocChange={setDraft} />
            </div>
          )}
          {editStyle === "split" && (
            <div className="plan-editor-split">
              <div className="cm-scroll">
                <CmEditor value={draft} onDocChange={setDraft} />
              </div>
              <div className="cm-scroll">
                <MarkdownPreview markdown={draft} />
              </div>
            </div>
          )}
          {editStyle === "viewer" && <MarkdownPreview markdown={draft} />}
        </div>
      </div>
    </section>
  );
}