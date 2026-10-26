import { Banner, Button } from "../../../shared/components/ui";
import { Modal } from "../../../shared/components/Modal";

/** 소스 삭제 확인 모달 — 프로젝트 삭제 모달과 동일 스타일 (파일명 입력 절차는 생략). */
export function SourceDeleteModal(props: {
  name: string;
  delBusy: boolean;
  delError: string | null;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Modal
      title="소스 삭제"
      labelledBy="source-delete-title"
      className="modal-del"
      onClose={props.onClose}
      closeDisabled={props.delBusy}
    >
      <p className="hint del-warn">소스는 휴지통 없이 영구 삭제되며 되돌릴 수 없습니다.</p>
      <p className="del-target">
        삭제할 소스: <strong>{props.name}</strong>
      </p>
      {props.delError && <Banner kind="error">{props.delError}</Banner>}
      <div className="modal-actions">
        <Button variant="ghost" onClick={props.onClose} disabled={props.delBusy}>
          취소
        </Button>
        <Button variant="danger" onClick={props.onConfirm} disabled={props.delBusy}>
          삭제
        </Button>
      </div>
    </Modal>
  );
}
