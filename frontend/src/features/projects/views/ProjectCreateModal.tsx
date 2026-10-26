import { Banner, Button } from "../../../shared/components/ui";
import { Modal } from "../../../shared/components/Modal";

const SLUG_RE = /^[a-z0-9][a-z0-9-]*$/;

/** 새 프로젝트 생성 모달 (FR-1.1) — 폼 상태는 ProjectsPage가 소유한다(닫았다 열어도 유지).
 *  슬러그 규칙은 백엔드와 동일 검증. */
export function ProjectCreateModal(props: {
  slug: string;
  title: string;
  owner: string;
  onSlug: (v: string) => void;
  onTitle: (v: string) => void;
  onOwner: (v: string) => void;
  formError: string | null;
  busy: boolean;
  onCreate: () => void;
  onClose: () => void;
}) {
  const slug = props.slug;
  const slugOk = SLUG_RE.test(slug.trim()) && slug.trim().length <= 64;

  return (
    <Modal
      title="새 프로젝트"
      labelledBy="new-project-title"
      onClose={props.onClose}
      closeDisabled={props.busy}
    >
      <form
        className="create-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (slugOk && props.title.trim() && !props.busy) props.onCreate();
        }}
      >
        <label>
          슬러그 <span className="hint">(영문 소문자·숫자·하이픈)</span>
          <input
            value={slug}
            onChange={(e) => props.onSlug(e.target.value)}
            placeholder="new-proposal"
            pattern="^[a-z0-9][a-z0-9\-]*$"
            autoFocus
            required
          />
        </label>
        <label>
          제목
          <input
            value={props.title}
            onChange={(e) => props.onTitle(e.target.value)}
            placeholder="2026 신규 사업 제안"
            required
          />
        </label>
        <label>
          담당자 <span className="hint">(선택)</span>
          <input value={props.owner} onChange={(e) => props.onOwner(e.target.value)} />
        </label>
        {props.formError && <Banner kind="error">{props.formError}</Banner>}
        <Button type="submit" disabled={!slugOk || !props.title.trim() || props.busy}>
          프로젝트 생성
        </Button>
        {!slugOk && slug.length > 0 && (
          <p className="hint">슬러그는 ASCII 소문자/숫자/하이픈(첫 글자 영숫자)만 허용됩니다.</p>
        )}
      </form>
    </Modal>
  );
}
