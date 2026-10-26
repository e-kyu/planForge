import { Button } from "../../../shared/components/ui";

/** 채팅 입력 — 자유 텍스트 전송(Enter) + 첫 턴 kick 버튼 (표현 전용).
 *  경로·본문은 만들지 않는다 — onSend/onKick이 viewmodel의 typed action을 호출한다. */
export function InterviewComposer(props: {
  draft: string;
  onDraft: (v: string) => void;
  busy: boolean;
  canInteract: boolean;
  isKick: boolean;
  onSend: () => void;
  onKick: () => void;
}) {
  return (
    <div className={props.isKick ? "chat-input chat-input-kick" : "chat-input"}>
      <textarea
        value={props.draft}
        placeholder={
          props.isKick
            ? "인터뷰를 시작하려면 아래 버튼을 누르세요"
            : "자유 텍스트로 보충·정정·잡담 (Enter 전송, Shift+Enter 줄바꿈)"
        }
        rows={2}
        disabled={props.busy || !props.canInteract}
        onChange={(e) => props.onDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (props.draft.trim() && !props.busy) props.onSend();
          }
        }}
      />
      {props.isKick ? (
        <Button onClick={props.onKick} disabled={props.busy}>
          인터뷰 시작 (가설 제시)
        </Button>
      ) : (
        <Button
          disabled={props.busy || !props.canInteract || !props.draft.trim()}
          onClick={props.onSend}
        >
          보내기
        </Button>
      )}
    </div>
  );
}
