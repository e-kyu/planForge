/** 도구 스키마(agents/tools.py)와 대응하는 카드 데이터 형태 — 인터뷰 View 공용. */
export type QuestionCard = {
  text: string;
  options?: { label: string; description?: string }[];
  allow_free?: boolean;
  suggestions?: string[]; // 추천 후보 칩 (소스·팩트 기반 — 클릭 시 자유 입력에 채움)
};

export type FactCard = { content: string; source?: string };
