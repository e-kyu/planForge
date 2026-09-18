import { useEffect, useRef } from "react";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { basicSetup } from "codemirror";
import { markdown } from "@codemirror/lang-markdown";
import { MergeView } from "@codemirror/merge";

/** CodeMirror 6 래퍼 — plan.md 편집/뷰/병합(이전 세대 대비 diff)에 쓴다. */
export function CmEditor(props: {
  value: string;
  readOnly?: boolean;
  onDocChange?: (doc: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const changeCb = useRef(props.onDocChange);
  changeCb.current = props.onDocChange;

  useEffect(() => {
    if (!host.current) return;
    const exts = [basicSetup, markdown(), EditorView.lineWrapping];
    if (props.readOnly) {
      exts.push(EditorState.readOnly.of(true), EditorView.editable.of(false));
    } else {
      exts.push(
        EditorView.updateListener.of((u) => {
          if (u.docChanged && changeCb.current) changeCb.current(u.state.doc.toString());
        }),
      );
    }
    const view = new EditorView({
      state: EditorState.create({ doc: props.value, extensions: exts }),
      parent: host.current,
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // value 초기화와 readOnly 전환에서만 재생성 — 내부 편집은 updateListener로 처리
  }, [props.readOnly]);

  // 외부에서 value가 바뀌면(세대 전환 등) 문서를 교체한다
  useEffect(() => {
    const view = viewRef.current;
    if (view && view.state.doc.toString() !== props.value) {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: props.value } });
    }
  }, [props.value]);

  return <div className="cm-host" ref={host} />;
}

/** 이전 세대(a) → 선택 세대(b) diff 뷰. */
export function CmDiff(props: { before: string; after: string }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!host.current) return;
    const opts = (doc: string) => ({
      doc,
      extensions: [basicSetup, markdown(), EditorView.editable.of(false)],
    });
    const mv = new MergeView({
      a: opts(props.before),
      b: opts(props.after),
      parent: host.current,
      revertControls: undefined,
    });
    return () => mv.destroy();
  }, [props.before, props.after]);
  return <div className="cm-host" ref={host} />;
}