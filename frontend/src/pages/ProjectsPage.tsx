import { useEffect, useState } from "react";
import { apiGet, apiPost, ApiError, type Project } from "../api/client";
import { Banner, Button, Loading } from "../components/ui";
import { navigate } from "../lib/hashRoute";

const SLUG_RE = /^[a-z0-9][a-z0-9-]*$/;

/** 프로젝트 목록 + 생성 (FR-1.1). 슬러그 규칙은 백엔드와 동일 검증. */
export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [owner, setOwner] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const p = await apiPost<Project>("/api/projects", {
        slug: slug.trim(),
        title: title.trim(),
        owner: owner.trim() || undefined,
      });
      setSlug("");
      setTitle("");
      setOwner("");
      navigate(`/projects/${p.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const slugOk = SLUG_RE.test(slug.trim()) && slug.trim().length <= 64;

  return (
    <>
      <h2 className="page-title">프로젝트</h2>
      {error && <Banner kind="error">{error}</Banner>}
      {projects === null ? (
        <Loading />
      ) : projects.length === 0 ? (
        <p className="hint">아직 프로젝트가 없습니다 — 아래에서 만들어 시작하세요.</p>
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
            </li>
          ))}
        </ul>
      )}

      <form
        className="card create-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (slugOk && title.trim() && !busy) void create();
        }}
      >
        <h3>새 프로젝트</h3>
        <label>
          슬러그 <span className="hint">(영문 소문자·숫자·하이픈)</span>
          <input
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="new-proposal"
            pattern="^[a-z0-9][a-z0-9-]*$"
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
        <Button type="submit" disabled={!slugOk || !title.trim() || busy}>
          프로젝트 생성
        </Button>
        {!slugOk && slug.length > 0 && (
          <p className="hint">슬러그는 ASCII 소문자/숫자/하이픈(첫 글자 영숫자)만 허용됩니다.</p>
        )}
      </form>
    </>
  );
}