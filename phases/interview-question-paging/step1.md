# Step 1: option-vertical — 선택지 1열 세로 레이아웃

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md`
- `/frontend/CLAUDE.md`
- `/docs/UI_GUIDE.md` (§레이아웃·§AI 슬롭 안티패턴 표 — 원시색/신규 토큰 금지, 과잉 장식 금지)
- `/frontend/src/features/interview/views/InterviewGates.tsx` — step 0에서 개편된
  AnswersCard (공용 페이저 + 단일 문항 렌더)
- `/frontend/src/features/interview/views/InterviewFeed.tsx` — step 0에서 개편된 StaticQuestions
- `/frontend/src/shared/styles/chat.css` — 작업 대상 (`.options` 규칙 + step 0 신규 클래스 점검)
- `/frontend/src/shared/styles/tokens.css` — 토큰 목록 확인용 (수정 금지)

step 0에서 만들어진 페이징 코드를 읽고 렌더 구조를 이해한 뒤, CSS만 고쳐
선택지 레이아웃을 바꾼다. 이 step은 **CSS 변경이 전부**다 — 컴포넌트를 수정하지 않는다.

## 배경 (요구사항)

인터뷰 문항의 선택지(`.options`)는 현재 `display: flex; flex-wrap: wrap; gap: 8px`
로 가로 흐름(2열 이상 줄바꿈) 배치다. 요구사항: 선택지 카드/버튼을 **1행에 1개씩
(세로 단일 열)** 나열하고, '직접 입력 (선택지 대신)' 입력창(`.free-input`)도 동일하게
1행 전폭 배치로 수직 통일한다.

## 작업

1. `.options`(chat.css L216–221 근처, 현재 `flex; flex-wrap: wrap; gap: 8px`)를
   세로 단일 열 스택으로 변경 — `flex-direction: column`(또는 grid 1열)으로 수정.
   하위 `.option` 버튼은 행 전폭 차지 — `.option`에 `width: 100%` 또는
   `align-self: stretch` 적용 (택일). 이유: 요구사항이 선택지를 세로로 길게
   단일 열로 보여주는 것이며, `.option`은 block 버튼이라 세로 플렉스만으로는
   내용만큼만 남는다.
2. 수직 배치 통일 점검 — 문항 본문 내 렌더 순서(추천 칩 `.suggest-row` → 선택지
   `.options` → 직접 입력 `.free-input`)가 세로로 쌓이는지 확인한다. `.free-input`은
   이미 `width: 100%`이므로 기존 규칙 유지. 문제가 있으면 `.options` 주변 간격
   (`margin-bottom: 6px` 등)만 미세 조정한다.
3. 토큰 원칙: 간격은 기존 값(8px) 유지 또는 `--space-2` 토큰으로 교체하라.
   원시색·신규 토큰 추가 금지 — 이유: 토큰 4종 세트 계약(루트 CLAUDE.md 원칙 7).
   이번 변경은 레이아웃 변경이므로 theme.py·tokens.css 값·계약 fixture는
   절차 대상 아니다 (건드리면 오히려 범위 위반이다).
4. step 0에서 추가된 페이저 클래스(점 인디케이터·내비게이션 행)의 레이아웃이
   문항 본문과 시각적으로 정렬되는지 확인하라 — 필요하면 간격만 보정하되
   구조 변경은 피한다.
5. 이력 카드(StaticQuestions)의 읽기 전용 옵션 목록(`.option-list`)도 세로 나열이
   기본이므로 별도 변경 불필요 — 확인만 하라.

## Acceptance Criteria

```bash
cd frontend && npm run build   # tsc --noEmit 포함 — 반드시 0 에러
```

커밋 전 `git status`로 `workspaces/`·`sources/`·`data/`·`backend/planforge/config.json`
등 ignored 경로가 섞이지 않았는지 확인한다 (루트 CLAUDE.md 규칙).

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - docs/UI_GUIDE.md §AI 슬롭 안티패턴 표 위반 요소(과잉 그림자·과도 전환·원시색
     신규 정의)를 넣지 않았는가?
   - CLAUDE.md 설계 원칙 계약 8개를 위반하지 않는가? (특히 원칙 7 — 토큰 값 변경 없음)
3. 결과에 따라 `phases/interview-question-paging/index.json`의 step 1을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`.
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`.
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단.

## 금지사항

- 컴포넌트(tsx) 파일을 수정하지 마라. 이유: 이 step은 CSS 레이아웃 변경만이 범위다 —
  JSX를 건드리면 step 0의 페이징 로직 회귀 위험이 생긴다. 단, 기존 규칙과의 충돌을
  해소하는 최소한의 CSS 클래스명 보정(컴파일 에러 해결이 아니라면)도 하지 않는다.
- `.options` 외의 기존 채팅·게이트·팩트 패널 클래스 규칙(`chat-layout`·`bubble`·
  `fact-*`·`compact-list` 등)을 변경하지 마라. 이유: 인터뷰 문항 레이아웃 외 화면
  회귀 위험.
- 토큰 값(`tokens.css`)·`theme.py`·`tests/fixtures/*`를 수정하지 마라. 이유: 원칙 7
  4종 세트 — 토큰 변경이 아니라 4종 세트 트리거를 만들지 않는다.
- 백엔드(`backend/`, `packages/`)를 수정하지 마라. 이유: 순수 프론트엔드 CSS 변경이다.
- 기존 테스트를 깨뜨리지 마라.