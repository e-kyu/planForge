import { useEffect, useState } from "react";
import { ChevronRight, Folder, Trash2, X } from "lucide-react";
import { Banner, Button, Empty, Loading } from "../../../shared/components/ui";
import { navigate } from "../../../shared/lib/hashRoute";
import { useProjects } from "../viewmodels/useProjects";
import type { Project } from "../../../api/client";

const SLUG_RE = /^[a-z0-9][a-z0-9-]*$/;

/** 프로젝트 목록 + 생성·삭제 (FR-1.1) — 표현 전용 View. 슬러그 규칙은 백엔드와 동일 검증. */
export default function ProjectsPage() {
  const {
    projects,
    error,
    notice,
    formError,
    busy,
    create,
    delTarget,
    delName,
    setDelName,
    delBusy,
    delError,
    openDelete,
    closeDelete,
    confirmDelete,
  } = useProjects();

  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [owner, setOwner] = useState("");
  const [open, setOpen] = useState(false);

  function closeForm() {
    setOpen(false);
  }

  // Esc로 팝업 닫기 — 삭제 확인 팝업이 우선 (작업 중에는 닫지 않음)
  useEffect(() => {
    if (!open && !delTarget) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (delTarget) {
        if (!delBusy) closeDelete();
      } else {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, delTarget, delBusy]);

  const slugOk = SLUG_RE.test(slug.trim()) && slug.trim().length <= 64;

  return (
    <>
      <div className="projects-head">
        <div>
          <h2>프로젝트</h2>
          <p>리포트 및 기획서 자동 생성을 위한 작업 공간을 관리합니다.</p>
        </div>
        <Button onClick={() => setOpen(true)}>새 프로젝트</Button>
      </div>
      {error && <Banner kind="error">{error}</Banner>}
      {notice && <Banner kind="ok">{notice}</Banner>}
      {projects === null ? (
        <Loading />
      ) : projects.length === 0 ? (
        <Empty>아직 프로젝트가 없습니다 — [새 프로젝트] 버튼으로 만들어 시작하세요.</Empty>
      ) : (
        <ul className="project-list">
          {projects.map((p) => (
            <ProjectRow key={p.id} p={p} delBusy={delBusy} onDelete={() => openDelete(p)} />
          ))}
        </ul>
      )}

      {open && (
        <div className="modal-overlay" onClick={busy ? undefined : closeForm}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-project-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h3 id="new-project-title">새 프로젝트</h3>
              <button
                className="modal-close"
                onClick={closeForm}
                disabled={busy}
                aria-label="닫기"
              >
                <X />
              </button>
            </div>
            <form
              className="create-form"
              onSubmit={(e) => {
                e.preventDefault();
                if (slugOk && title.trim() && !busy) void create(slug, title, owner);
              }}
            >
              <label>
                슬러그 <span className="hint">(영문 소문자·숫자·하이픈)</span>
                <input
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  placeholder="new-proposal"
                  pattern="^[a-z0-9][a-z0-9\-]*$"
                  autoFocus
                  required
                />
              </label>
              <label>
                제목
                <input value={title} onChange={(e) => setTitle(e.target.value)}
                       placeholder="2026 신규 사업 제안" required />
              </label>
              <label>
                담당자 <span className="hint">(선택)</span>
                <input value={owner} onChange={(e) => setOwner(e.target.value)} />
              </label>
              {formError && <Banner kind="error">{formError}</Banner>}
              <Button type="submit" disabled={!slugOk || !title.trim() || busy}>
                프로젝트 생성
              </Button>
              {!slugOk && slug.length > 0 && (
                <p className="hint">슬러그는 ASCII 소문자/숫자/하이픈(첫 글자 영숫자)만 허용됩니다.</p>
              )}
            </form>
          </div>
        </div>
      )}

      {delTarget && (
        <div className="modal-overlay" onClick={delBusy ? undefined : closeDelete}>
          <div
            className="modal modal-del"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-project-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h3 id="delete-project-title">프로젝트 삭제</h3>
              <button
                className="modal-close"
                onClick={closeDelete}
                disabled={delBusy}
                aria-label="닫기"
              >
                <X />
              </button>
            </div>
            <p className="hint del-warn">
              프로젝트와 관련 데이터(인터뷰·팩트·plan·산출물)와 워크스페이스 파일이
              영구 삭제되며 되돌릴 수 없습니다.
            </p>
            <p className="del-target">
              삭제할 프로젝트: <strong>{delTarget.title}</strong>{" "}
              <span className="project-slug">{delTarget.slug}</span>
            </p>
            <form
              className="create-form"
              onSubmit={(e) => {
                e.preventDefault();
                if (delName === delTarget.title && !delBusy) void confirmDelete();
              }}
            >
              <label>
                확인 — 프로젝트명 <strong>"{delTarget.title}"</strong>을(를) 그대로 입력하세요
                <input
                  value={delName}
                  onChange={(e) => setDelName(e.target.value)}
                  placeholder={delTarget.title}
                  autoFocus
                />
              </label>
              {delError && <Banner kind="error">{delError}</Banner>}
              <Button
                type="submit"
                variant="danger"
                disabled={delName !== delTarget.title || delBusy}
              >
                영구 삭제
              </Button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}

function ProjectRow(props: { p: Project; delBusy: boolean; onDelete: () => void }) {
  const p = props.p;
  return (
    <li>
      <button className="project-row" onClick={() => navigate(`/projects/${p.id}`)}>
        <span className="project-top">
          <span className={`badge badge-global badge-${p.status}`}>
            {p.status === "active" ? "진행 중" : "보관"}
          </span>
        </span>
        <span className="project-name">
          <Folder aria-hidden="true" />
          {p.title}
        </span>
        <span className="project-meta">
          {p.slug}
          {p.owner && <span className="project-owner">{p.owner}</span>}
        </span>
        <span className="project-foot">
          <span className="project-date">{p.created_at.slice(0, 10)}</span>
          <span className="project-open" aria-hidden="true">
            열기
            <ChevronRight />
          </span>
        </span>
      </button>
      <button
        type="button"
        className="project-del"
        disabled={props.delBusy}
        onClick={props.onDelete}
        aria-label={`${p.title} 삭제`}
        title="삭제"
      >
        <Trash2 aria-hidden="true" />
      </button>
    </li>
  );
}