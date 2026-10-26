import { useState } from "react";
import { Banner, Button, Empty, Loading } from "../../../shared/components/ui";
import { useProjects } from "../viewmodels/useProjects";
import { ProjectCreateModal } from "./ProjectCreateModal";
import { ProjectDeleteModal } from "./ProjectDeleteModal";
import { ProjectRow } from "./ProjectRow";

/** 프로젝트 목록 + 생성·삭제 (FR-1.1) — 표현 전용 View.
 *  생성 폼의 로컬 상태(슬러그·제목·담당자)는 닫았다 열어도 유지되도록 이 컨테이너가 소유한다.
 *  서버 상태·삭제 상태머신은 useProjects, 모달의 Esc·overlay 닫기는 shared Modal이 담당. */
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
        <ProjectCreateModal
          slug={slug}
          title={title}
          owner={owner}
          onSlug={setSlug}
          onTitle={setTitle}
          onOwner={setOwner}
          formError={formError}
          busy={busy}
          onCreate={() => void create(slug, title, owner)}
          onClose={() => {
            if (!busy) closeForm();
          }}
        />
      )}

      {delTarget && (
        <ProjectDeleteModal
          target={delTarget}
          delName={delName}
          onDelName={setDelName}
          delBusy={delBusy}
          delError={delError}
          onConfirm={() => void confirmDelete()}
          onClose={() => {
            if (!delBusy) closeDelete();
          }}
        />
      )}
    </>
  );
}
