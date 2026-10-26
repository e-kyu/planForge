import { Banner, Button } from "../../../shared/components/ui";
import { Modal } from "../../../shared/components/Modal";
import type { Project } from "../../../api/client";

/** 프로젝트 영구 삭제 모달 — 안전장치로 프로젝트명을 그대로 입력해야 실행된다.
 *  입력값·busy 상태는 useProjects(viewmodel)가 소유한다. */
export function ProjectDeleteModal(props: {
  target: Project;
  delName: string;
  onDelName: (v: string) => void;
  delBusy: boolean;
  delError: string | null;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Modal
      title="프로젝트 삭제"
      labelledBy="delete-project-title"
      className="modal-del"
      onClose={props.onClose}
      closeDisabled={props.delBusy}
    >
      <p className="hint del-warn">
        프로젝트와 관련 데이터(인터뷰·팩트·plan·산출물)와 워크스페이스 파일이
        영구 삭제되며 되돌릴 수 없습니다.
      </p>
      <p className="del-target">
        삭제할 프로젝트: <strong>{props.target.title}</strong>{" "}
        <span className="project-slug">{props.target.slug}</span>
      </p>
      <form
        className="create-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (props.delName === props.target.title && !props.delBusy) props.onConfirm();
        }}
      >
        <label>
          확인 — 프로젝트명 <strong>"{props.target.title}"</strong>을(를) 그대로 입력하세요
          <input
            value={props.delName}
            onChange={(e) => props.onDelName(e.target.value)}
            placeholder={props.target.title}
            autoFocus
          />
        </label>
        {props.delError && <Banner kind="error">{props.delError}</Banner>}
        <Button
          type="submit"
          variant="danger"
          disabled={props.delName !== props.target.title || props.delBusy}
        >
          영구 삭제
        </Button>
      </form>
    </Modal>
  );
}
