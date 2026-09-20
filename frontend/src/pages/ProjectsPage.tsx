import { useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost, ApiError, type Project } from "../api/client";
import { Banner, Button, Loading } from "../components/ui";
import { navigate } from "../lib/hashRoute";

const SLUG_RE = /^[a-z0-9][a-z0-9-]*$/;

/** 프로젝트 목록 + 생성·삭제 (FR-1.1). 슬러그 규칙은 백엔드와 동일 검증. */
export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [owner, setOwner] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const [delTarget, setDelTarget] = useState<Project | null>(null);
  const [delName, setDelName] = useState("");
  const [delBusy, setDelBusy] = useState(false);
  const [delError, setDelError] = useState<string | null>(null);

  async function load() {
    try {
      setProjects(await apiGet<Project[]>("/api/projects"));
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }
  useEffect(() => {
    void load();
  }, []);

  function closeForm() {
    setOpen(false);
    setFormError(null);
  }

  function openDelete(p: Project) {
    setDelTarget(p);
    setDelName("");
    setDelError(null);
    setNotice(null);
  }

  function closeDelete() {
    setDelTarget(null);
    setDelName("");
    setDelError(null);
  }

  // Esc로 팝업 닫기 — 삭제 확인 팝업이 우선 (작업 중에는 닫지 않음)
  useEffect(() => {
    if (!open && !delTarget) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (delTarget) {
        if (!delBusy) closeDelete();
      } else {
        closeForm();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, delTarget, delBusy]);

  async function create() {
    setBusy(true);
    setFormError(null);
    try {
      const p = await apiPost<Project>("/api/projects", {
        slug: slug.trim(),
        title: title.trim(),
        owner: owner.trim() || undefined,
      });
      setSlug("");
      setTitle("");
      setOwner("");
      setOpen(false);
      navigate(`/projects/${p.id}`);
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    if (!delTarget || delBusy) return;
    setDelBusy(true);
    setDelError(null);
    try {
      await apiDelete(`/api/projects/${delTarget.id}`);
      const gone = delTarget.title;
      closeDelete();
      setNotice(`삭제되었습니다: ${gone}`);
      await load();
    } catch (e) {
      setDelError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setDelBusy(false);
    }
  }

  const slugOk = SLUG_RE.test(slug.trim()) && slug.trim().length <= 64;

  return (
    <>
      <h2 className="page-title">프로젝트</h2>
      {error && <Banner kind="error">{error}</Banner>}
      {notice && <Banner kind="ok">{notice}</Banner>}
      <div className="list-head">
        <Button onClick={() => setOpen(true)}>새 프로젝트</Button>
      </div>
      {projects === null ? (
        <Loading />
      ) : projects.length === 0 ? (
        <p className="hint">아직 프로젝트가 없습니다 — [새 프로젝트] 버튼으로 만들어 시작하세요.</p>
      ) : (
        <ul className="project-list">
          {projects.map((p) => (
            <li key={p.id}>
              <button className="project-row" onClick={() => navigate(`/projects/${p.id}`)}>
                <span className="project-title">{p.title}</span>
                <span className="project-slug">{p.slug}</span>
                <span className={`badge badge-${p.status}`}>
                  {p.status === "active" ? "진행 중" : "보관"}
                </span>
              </button>
              <button
                type="button"
                className="project-del"
                disabled={delBusy}
                onClick={() => openDelete(p)}
                aria-label={`${p.title} 삭제`}
              >
                삭제
              </button>
            </li>
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
                ×
              </button>
            </div>
            <form
              className="create-form"
              onSubmit={(e) => {
                e.preventDefault();
                if (slugOk && title.trim() && !busy) void create();
              }}
            >
              <label>
                슬러그 <span className="hint">(영문 소문자·숫자·하이픈)</span>
                <input
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  placeholder="new-proposal"
                  pattern="^[a-z0-9][a-z0-9-]*$"
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
                ×
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