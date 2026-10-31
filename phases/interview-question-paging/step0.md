# Step 0: interview-paging — 답변 카드 문항 페이징 + 이력 카드 일관 적용

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/frontend/CLAUDE.md`
- `/docs/ARCHITECTURE.md` (프론트엔드 feature-MVVM 섹션)
- `/docs/INTERVIEW-TURN-CONTRACT.md` (프론트 렌더 계약 L39–43, 제출 계약 L64–68)
- `/frontend/src/features/interview/views/InterviewGates.tsx` — 작업 대상 (AnswersCard)
- `/frontend/src/features/interview/views/InterviewFeed.tsx` — 작업 대상 (StaticQuestions)
- `/frontend/src/features/interview/viewmodels/useInterview.ts` — `AnswerDraft`·`answerItems`·`suggestedAnswer` (수정 금지, 계약 이해용)
- `/frontend/src/features/interview/views/InterviewPanel.tsx` — AnswersCard 호출부 (props 이해용)
- `/frontend/src/shared/styles/chat.css` — 기존 인터뷰 클래스 (신규 페이저 클래스 추가 위치)
- `/frontend/src/shared/components/ui.tsx` — Button variant 재사용

기존 코드를 꼼꼼히 읽고 설계 의도를 이해한 뒤 작업하라. 이번 step은
**프론트엔드 렌더 방식 변경만** 한다 — 제출 와이어 계약은 변경하지 않는다.

## 배경 (요구사항)

인터뷰 답변 카드(`AnswersCard`)는 현재 라운드의 최대 4문항(`props.questions`)을
`<ol className="question-list">` 안에 전부 나열한다. 요구사항: 라운드 내 문항을
**한 번에 1개씩만** 노출하는 step-by-step 페이징 UI로 개편한다. 또한 채팅 이력의
질문 카드(이력 리플레이 `StaticQuestions`)도 동일한 문항 단위 페이징으로 일관 적용한다
(사용자 확정 사항 — 이력 카드도 1문항씩 + 이전/다음).

확정된 UX 결정:

- 진행 표시 = 점(dot) 인디케이터 (문항 수만큼, 현재 위치 강조) — "문항 1/4" 텍스트는 쓰지 않는다.
- [이전] 버튼은 첫 문항에서 `disabled`, [다음] 버튼은 마지막 문항 전까지 표시.
- 마지막 문항 화면에서만 제출 액션 노출: '답변 제출'(primary) + 추천 존재 시
  '추천으로 전체 제출'(ghost). 중간 문항 화면에는 제출 버튼을 노출하지 않는다.
- 문항 이동은 답변 여부와 무관한 자유 이동이다 — [다음]을 답변 완료 조건으로 게이팅하지
  않는다. 이유: 미답변 문항은 기존 계약대로 서버가 `(모름)` 마킹한다
  (`answerItems`는 미답변 문항을 스킵한다 — 이 동작을 변경하지 않는다).

## 작업

### 1. 공용 페이저 프리미티브 (viewmodels)

`frontend/src/features/interview/viewmodels/`에 신규 훅 파일(예: `useQuestionPager.ts`)을
만든다. AnswersCard(활성 답변 카드)와 StaticQuestions(이력 카드)가 같은 프리미티브로
페이징해야 일관성이 유지된다. 인터페이스(시그니처)만 제시한다 — 내부 구현은 재량:

```ts
// viewmodels/useQuestionPager.ts
export function useQuestionPager(questions: QuestionCard[] | unknown[]): {
  current: number;      // 현재 문항 인덱스 (0-based)
  total: number;
  isFirst: boolean;
  isLast: boolean;
  prev: () => void;
  next: () => void;
}
```

핵심 규칙:

- `inputs` 배열(`questions` 등)의 **식별자가 바뀌면(current 라운드 교체)** 인덱스를 0으로
  리셋한다. 이유: 서버 주도로 `pending_questions`가 다음 라운드 배열로 교체될 때
  이번 라운드 문항수가 다를 수 있고, 이전 라운드 마지막 위치에 있으면 범위를 벗어난다.
- 리셋 트리거는 `useEffect(() => setCurrent(0), [questions])` 또는 배열 참조 비교 중
  재량 택일하되, StrictMode 이중 렌더에서 안전하게 동작해야 한다.
- 훅은 서버 데이터 로직(fetch·쿼리)을 포함하지 않는다 — 표현 직전의 로컬 UI 상태일 뿐이다.

### 2. AnswersCard 페이징 개편 (`frontend/src/features/interview/views/InterviewGates.tsx`)

`AnswersCard`(L9–90)를 아래처럼 개편하라. 시그니처와 클래스 재사용 계약은 유지한다:

```tsx
export function AnswersCard(props: {
  questions: QuestionCard[];
  answers: AnswerDraft;
  round?: number;
  summary?: string | null;
  onPick: (i: number, patch: { option?: number; free?: string }) => void;
  onSubmit: () => void;
  onSubmitAll: () => void;
  busy: boolean;
})  // 시그니처 변경 없음
```

- 렌더는 1문항만: `props.questions[current]`를 기존 문항 렌더 요소
  (`q-text` → `suggest-row`/`suggest-chip` → `options`/`option`/`option-picked`/
  `option-label`/`option-desc` → `free-input`)로 그대로 렌더한다.
  `onPick(i, ...)`의 `i`는 **`props.questions` 배열 기준 실제 인덱스**(= `current`)여야
  한다 — `AnswerDraft`는 배열 인덱스 키이므로 페이징이 키를 바꾸면 안 된다.
- 점 인디케이터: 라운드 목표 부제(`chat-card-title`)와 문항 본문 사이에 배치.
  문항 수만큼 점을 가로로 나열하고, current 점만 강조. `total === 1`이면
  인디케이터·이전/다음 모두 숨긴다(단일 문항 라운드는 페이징이 무의미하다).
- [이전]/[다음]: 카드 하단 액션 영역 위에 배치한다. [이전]은 `current === 0`에서
  `disabled`, [다음]은 마지막 문항이 아닐 때 표시. 공용 UI `Button` 컴포넌트
  (`shared/components/ui.tsx`)를 재사용하라 (variant 재량 — ghost 권장).
- 마지막 문항: [다음] 대신 기존 `.center-actions` 행을 렌더 — `hasSuggestions`면
  '추천으로 전체 제출'(ghost, 기존 title 속성 유지) + '답변 제출'(primary).
  마지막 문항이 아니면 이 행을 노출하지 않는다.
- 유지 계약 (변경 금지):
  - `onPick` 시그니처·`AnswerDraft`(인덱스별 option/free 상호배타)·`onSubmit`/
    `onSubmitAll`·`busy` 처리 전부 기존 그대로.
  - 추천 칩 동작(클릭 시 free에 채움, 즉시 제출 아님 — 결정 20) 유지.
  - `InterviewPanel.tsx`의 `submitAllWithSuggestions`·`answerItems` 호출부는 수정 불필요.
  - `.free-input` 클래스와 '답변 제출' 버튼 **텍스트**는 반드시 유지 — `frontend/e2e-smoke.mjs`
    (L122–139)가 `.free-input`·`button:has-text('답변 제출')`·'승인 · 기록' 선택자에 의존한다.

### 3. StaticQuestions 페이징 일관 적용 (`frontend/src/features/interview/views/InterviewFeed.tsx`)

`StaticQuestions`(L150–170, 이력 `event:questions` 카드의 읽기 전용 본문)을
공용 페이저로 아래처럼 개편하라:

- 1문항씩 렌더 + 점 인디케이터 + [이전]/[다음] — 활성 답변 카드와 동일한 페이저 프리미티브 사용.
- 문항 본문은 기존 방식(`q.text` + 옵션 목록, 읽기 전용)을 단일 문항으로 축소한다.
  현재 `.compact-list`+`.option-list` 구조는 문항별 `<li>` 나열이므로, 단일 문항 렌더로
  바꾼다 (래퍼 클래스는 기존 것을 재사용하되 `compact-list`의 `<ol>` 번호 매김은
  단일 문항에 어울리도록 재량 조정 — 예: `div`+`q-text` 재사용).
- **입력창·제출 버튼 없음** — 이력은 확정 완료 기록이므로 편집 UI를 만들지 않는다.
- `Bubble`·`StaticCard`·`renderMessage`(메시지 파싱) 구조는 바꾸지 않는다 —
  `StaticQuestions` 본문만 교체한다.
- InterviewFeed L25의 'e2e 선택자 보존' 주석을 정확히 갱신하라:
  e2e-smoke의 선택자(`.free-input`·'답변 제출'·'승인 · 기록')는 모두 활성
  게이트/AnswersCard/FactGate 대상이므로 StaticQuestions 변경 영향이 없음을 확인하고,
  'DOM 구조·클래스 유지' 주석이 StaticQuestions까지 포괄하지 않도록 정리한다.
- `renderMessage`에서 `p.questions` 캐스팅 등 데이터 해석 로직은 건드리지 않는다.

### 4. 페이저 CSS (`frontend/src/shared/styles/chat.css`)

페이저(점 인디케이터 + 내비게이션 행)용 신규 클래스를 chat.css에 추가한다.
클래스명은 kebab-case로 재량 (예: `.q-dots`·`.q-dot`·`.q-dot-active`·`.q-pager`).

- 기존 클래스(`chat-card`·`question-list`·`q-text`·`suggest-*`·`options`·`option-*`·
  `free-input`·`center-actions`)의 기존 규칙을 이 step에서 변경하지 마라 —
  선택지 1열 레이아웃은 다음 step(option-vertical)의 범위다.
- 신규 클래스는 디자인 토큰만 참조한다: `--blue`·`--line`·`--surface-sub`·`--text-sub`·
  `--radius-sm`·`--speed`·`--space-*` 등 (tokens.css에 존재하는 토큰). 원시색·신규
  토큰 정의 금지. 이유: 토큰 4종 세트 계약(루트 CLAUDE.md 원칙 7) — 이번 변경은
  토큰 변경이 아니며, 토큰을 추가하면 4종 세트 절차가 파생된다.
- `docs/UI_GUIDE.md` §AI 슬롭 안티패턴 표 위반 요소(과잉 그림자·과도 전환 등)를
  추가하지 마라.

## Acceptance Criteria

```bash
cd frontend && npm run build   # tsc --noEmit 포함 — 반드시 0 에러
```

추가 자점 검증 (커맨드 실행은 각자 판단):

- `npm run build` 통과 외에, 개편된 AnswersCard/StaticQuestions 코드 리뷰로 다음을 확인한다:
  - 1문항만 렌더되고, 인덱스가 `AnswerDraft` 키 정합성을 유지하는가
    (문항 2에서 선택한 옵션이 문항 0으로 이동하면 옵션 강조가 같이 이동해야 정상이다)?
  - questions 교체(라운드 전환) 시 인덱스가 0으로 리셋되는가?
  - `total === 1`일 때 페이징 UI가 노출되지 않는가?

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - docs/ARCHITECTURE.md feature-MVVM 규칙(§4.3 View에서 서버 데이터 로직 금지)을
     지키는가? — 페이저 훅은 viewmodels/에 둔다.
   - docs/INTERVIEW-TURN-CONTRACT.md L39–68 계약(options 조건부 렌더·allow_free 입력·
     제출 와이어 `AnswerItem[]`)을 유지하는가?
   - CLAUDE.md 설계 원칙 계약 8개를 위반하지 않는가? (특히 원칙 7 — 토큰 값 변경 없음)
3. 결과에 따라 `phases/interview-question-paging/index.json`의 step 0을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`.
     summary에는 생성/수정 파일 경로(공용 페이저 훅 파일명 포함)를 명시하라 —
     다음 step이 참조한다.
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`.
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단.

## 금지사항

- `viewmodels/useInterview.ts`(`answerItems`·`suggestedAnswer`·`run`)와
  `models/interviewApi.ts`를 수정하지 마라. 이유: 제출 와이어(`POST /answers
  {answers: AnswerItem[]}`)는 계약이며, 이번 step은 렌더 방식만 변경한다.
- `InterviewPanel.tsx`에서 AnswersCard의 props 전달 방식을 바꾸지 마라 (시그니처 유지).
  유일한 예외: 상위에서 `key={...}` 추가가 필요하면 허용한다 — 이는 페이저 리셋의
  합법적 수단이다.
- 토큰 값(`tokens.css`)·`theme.py`·테스트 fixture(`tests/fixtures/*`)를 수정하지 마라.
  이유: 이번 작업은 토큰 변경이 아니며, 토큰 손대면 4종 세트 절차 위반이 된다.
- `FactGate`/`KeyGate`는 수정하지 마라. 이유: 요구사항 범위 밖 ('승인 · 기록' 게이트는
  e2e 선택자 의존도 있다).
- 백엔드(`backend/`, `packages/`) 전체를 코드 수정 대상으로 건드리지 마라. 이유:
  이번 작업은 순수 프론트엔드 렌더 개편이다.
- 기존 테스트를 깨뜨리지 마라 — 백엔드 회귀(`python -m pytest tests/test_agents_tools.py
  tests/test_interview_api.py -q`)는 건드리지 않으면 자동으로 안전하다 (수정하면 위반).