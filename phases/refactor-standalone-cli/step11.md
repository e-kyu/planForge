# Step 11: frontend-mvvm-cleanup

## 읽어야 할 파일

- `/frontend/CLAUDE.md` — View fetch 금지, feature-MVVM
- `/docs/ADR.md` — D-9/D-10, 편차 4(DOM/UI 효과는 View 허용), 결정 19(인터뷰 렌더)
- `/frontend/src/features/interview/views/InterviewPanel.tsx`
- `/frontend/src/features/interview/viewmodels/useInterview.ts`
- `/frontend/src/features/interview/models/interviewApi.ts`
- `/frontend/src/features/projects/views/ProjectsPage.tsx`
- `/frontend/src/features/sources/views/SourcesPanel.tsx`, `OverviewEditor.tsx`
- `/frontend/src/features/outputs/views/OutputsPanel.tsx`, `models/outputsApi.ts`
- `/frontend/src/features/review/views/ReviewPanel.tsx`
- `/frontend/src/features/plan/views/PlanPanel.tsx`
- `/frontend/src/features/project/views/ActivityPill.tsx`, `HeaderMetrics.tsx`
- `/frontend/src/features/interview/views/FactSidePanel.tsx`
- `/frontend/src/shared/components/ui.tsx`
- `/frontend/src/api/client.ts`
- Step 10 산출물: `shared/lib/format.ts`, `shared/components/SegToggle.tsx`, `shared/lib/jobs.ts`

## 배경

`InterviewPanel`이 엔드포인트 경로/본문을 직접 만들고, 모달·삭제 확인·대형 View가
복제·비대해져 있다. MVVM 위반을 없애고 컴포넌트를 분할한다. **동작·문구·DOM 구조·
CSS 클래스·SSE 계약은 불변**이다.

## 작업

### 1. 인터뷰 요청 조립을 viewmodel/model로 이동

`interviewApi.ts`에 턴 요청 빌더를 추가한다(실제 POST가 아니라 apiSSE용 path/body):

```ts
export type InterviewTurnRequest = { path: string; body: unknown };
export function turnRequest(sid: number, kind: "turn" | "kick" | "answers" |
  "facts-confirm" | "key-messages", payload?: unknown): InterviewTurnRequest;
```

- `turn`: `/api/interview/sessions/${sid}/turn`, body `{ message }`
- `kick`: `/kick`, body `{}`
- `answers`: `/answers`, body `{ answers: items }`
- `facts-confirm`: `/facts/confirm`, body `{ approve, edits }`
- `key-messages`: `/key-messages`, body `{ approve, feedback }`

`useInterview`가 typed action을 노출한다:

```ts
submitTurn(message: string): Promise<boolean>;
submitKick(): Promise<boolean>;
submitAnswers(items: { index: number; option?: number; free_text?: string }[]): Promise<boolean>;
submitFactsConfirm(approve: boolean, edits: unknown[]): Promise<boolean>;
submitKeyMessages(approve: boolean, feedback?: string): Promise<boolean>;
```

기존 `run(path, body)`의 apiSSE 소비·이벤트 처리·무효화·busy/error/streaming 상태
전이는 그대로 재사용한다. View는 더 이상 경로/본문을 만들지 않는다.
`submitAllWithSuggestions` 같은 View 로직은 viewmodel로 옮기거나, View가 typed action에
데이터만 넘기도록 정리한다(답변 조립은 viewmodel이 담당).

### 2. Modal 공유 컴포넌트

`shared/components/Modal.tsx`를 만든다:

```ts
export function Modal(props: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  labelledBy?: string;
  className?: string;
}): JSX.Element;
```

- 기존 마크업의 overlay/panel 클래스, `role="dialog"`, `aria-modal`, 닫기 버튼,
  overlay 클릭 닫기를 유지한다.
- Esc 처리는 기존 각 화면의 `useEffect` 리스너를 Modal로 옮긴다. DOM/UI 효과는
  View에 남아도 된다(편차 4).
- `ProjectsPage` 생성/삭제, `SourcesPanel` 삭제가 사용한다.
- 삭제 확인 UX 차이(프로젝트명 입력 vs 단순 확인)는 각 화면에 유지한다.

### 3. `apiText`

`api/client.ts`에 `apiText(path: string): Promise<string>`를 추가한다:

- `fetch`, `!res.ok`면 `ApiError`, 아니면 `res.text()`.
- `outputsApi.fetchOutputText`가 raw fetch 대신 `apiText`를 쓴다.
- 다운로드 동작·URL은 불변.

### 4. 대형 View 분할

- `ProjectsPage`: `ProjectCreateModal`, `ProjectDeleteModal`, `ProjectRow`, 목록
  컨테이너로 분리. 상태·API 호출은 기존 viewmodel을 유지.
- `InterviewPanel`이 300줄을 넘으면 메시지 목록/입력/게이트 카드 렌더링을 별도
  파일로 분리한다. **동일한 DOM 구조·클래스**를 유지해 e2e 선택자가 깨지지 않게 한다.
- `SourcesPanel`의 `table()` 클로저와 삭제 모달을 별도 컴포넌트로 분리.
- `OutputsPanel`/`ReviewPanel`/`PlanPanel`은 중첩 삼항과 반복 배너 렌더를 helper로
  정리하되, 렌더 결과는 동일하게 유지.

### 5. 삼항 정리

`HeaderMetrics`, `ActivityPill`, `ReviewPanel`, `OutputsPanel`, `FactSidePanel`,
`ui.tsx`의 중첩 삼항을 lookup map/early-return helper로 바꾼다. 출력 문구·톤·클래스는
동일해야 한다.

### 6. 유예

- query key 중앙화, 캐시 중복 제거, 삭제 상태머신 통합, lint 도구 도입은 하지 않는다.

## Acceptance Criteria

```powershell
npm --prefix frontend run build
```

## 검증 절차

1. AC를 실행한다.
2. 체크리스트:
   - View에서 fetch/서버 데이터 로직이 사라졌는가?
   - SSE 경로·이벤트 처리·무효화 동작이 동일한가?
   - 삭제 확인 UX와 안전장치(프로젝트명 입력)가 유지되는가?
   - DOM 구조·클래스·문구가 동일한가?
3. `phases/refactor-standalone-cli/index.json`의 step 11을 갱신한다.

## 금지사항

- query key·invalidation·refetchInterval을 바꾸지 마라. 이유: 조용한 리페치/캐시
  동작 변경이다(유예).
- SSE 이벤트 계약·재시도·메시지 영속화를 바꾸지 마라. 이유: 인터뷰 턴 계약(D6).
- 삭제 안전장치(프로젝트명 확인)를 약화하지 마라.
- 새 상태관리 라이브러리나 lint 도구를 도입하지 마라. 이유: 이번 범위 밖이다.
