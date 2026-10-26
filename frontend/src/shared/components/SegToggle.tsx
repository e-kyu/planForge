/** 표시 방식 세그먼트 토글 — 보기·대비 = 코드|뷰어, 편집 = 코드|분할|뷰어 (3모드 동일 UI).
 *  PlanPanel·OverviewEditor가 공유한다. 클래스(plan-seg*)·동작은 원본 그대로. */
export default function SegToggle<T extends string>(props: {
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
