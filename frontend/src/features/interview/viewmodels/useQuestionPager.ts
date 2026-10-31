import { useEffect, useState } from "react";

/** 문항 페이저 — 활성 답변 카드(AnswersCard)·이력 카드(StaticQuestions)가 공유하는
 *  step-by-step 페이징 프리미티브 (표현 직전의 로컬 UI 상태 — 서버 데이터 로직 없음).
 *  questions 식별자가 바뀌면(라운드 교체) 위치를 첫 문항으로 리셋한다 — 서버가
 *  pending_questions를 교체 주도하므로 이전 라운드의 마지막 위치가 다음 라운드 문항수를
 *  벗어나지 않도록 한다. 리셋(effect의 setCurrent(0))은 멱등 — StrictMode 이중
 *  effect에도 안전하다. 반환 current는 항상 유효 범위로 clamp한다 (리셋 전 1렌더 차이 방어). */
export function useQuestionPager(questions: readonly unknown[]): {
  current: number; // 현재 문항 인덱스 (0-based, 항상 유효 범위)
  total: number;
  isFirst: boolean;
  isLast: boolean;
  prev: () => void;
  next: () => void;
} {
  const total = questions.length;
  const [raw, setRaw] = useState(0);

  // 라운드 교체(배열 식별자 변경) 시 첫 문항으로 리셋 — TanStack structural sharing 덕에
  // 내용이 같은 재fetch는 같은 참조를 유지하므로 무의미한 리셋은 발생하지 않는다.
  useEffect(() => {
    setRaw(0);
  }, [questions]);

  const current = total > 0 ? Math.min(raw, total - 1) : 0;
  return {
    current,
    total,
    isFirst: current === 0,
    isLast: current >= Math.max(total - 1, 0),
    prev: () => setRaw((c) => Math.max(0, c - 1)),
    next: () => setRaw((c) => Math.min(total - 1, c + 1)),
  };
}