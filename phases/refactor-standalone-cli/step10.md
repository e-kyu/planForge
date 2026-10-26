# Step 10: frontend-shared-foundation

## 읽어야 할 파일

- `/frontend/CLAUDE.md` — feature-MVVM·View fetch 금지
- `/docs/ADR.md` — D-9/D-10, 결정 15(jobs 폴링 소유자), 16(fmtDateTime)
- `/frontend/src/shared/components/ui.tsx`
- `/frontend/src/shared/lib/jobs.ts`, `useActiveJobs.ts`
- `/frontend/src/features/plan/views/PlanPanel.tsx`
- `/frontend/src/features/sources/views/OverviewEditor.tsx`, `SourcesPanel.tsx`
- `/frontend/src/features/sources/viewmodels/useOverview.ts`, `useSources.ts`
- `/frontend/src/features/outputs/views/OutputsPanel.tsx`
- `/frontend/src/features/review/views/ReviewPanel.tsx`
- `/frontend/src/features/project/viewmodels/useProjectShell.ts`
- `/frontend/src/features/plan/viewmodels/usePlans.ts`
- `/frontend/src/features/projects/views/ProjectsPage.tsx`
- `/frontend/src/shared/styles/tokens.css` — 토큰 변경 금지

## 배경

프론트에 날짜/버전 포맷, SegToggle, 업로드 상한, 상태 라벨, 활성 잡 predicate가
복제돼 있다. **안전한 공유 유틸·컴포넌트만** 추출한다. query key·캐시 범위·API 호출
경로는 바꾸지 않는다.

## 작업

### 1. `shared/lib/format.ts`

```ts
export function formatVersion(n: number): string;      // `v${padStart(2,"0")}`
export function fmtDateTime(iso: string | unknown): string;
export function fmtDate(iso: string | unknown): string;
export function fmtBytes(n: number): string;
export function formatEpochSeconds(sec: number): string;
```

- 구현은 `ui.tsx`의 현재 `fmtDateTime`/`fmtDate`/`fmtBytes`와 동일하게 옮긴다.
- `ui.tsx`는 기존 이름을 `format.ts`에서 재수출해 다른 import를 깨지 않는다.
- `formatEpochSeconds`는 `SourcesPanel.tsx`의 `fmtEpoch`와 동일한 로컬 시각 포맷.

### 2. 공유 상수/선택자

- `shared/lib/uploadLimits.ts`: `MAX_SOURCE_MB = 2`, `MAX_ZIP_MB = 30`.
  `useOverview`/`useSources`의 중복 상수를 대체한다.
- `shared/lib/labels.ts`: plan 상태·job 상태 라벨을 한 어휘로 모은다. 기존 화면 문구를
  바꾸지 않도록 **현재 사용 중인 문구를 그대로** 옮긴다. 서로 다른 문구(`승인됨` vs
  `승인`)는 이번 step에서 통일하지 말고, 각각의 키를 유지한다.
- `shared/lib/plans.ts::latestApproved(plans, doc?)` — `OutputsPanel`/`ReviewPanel`의
  선택 로직을 대체하되 doc 필터 동작 차이는 보존한다.
- `shared/lib/messages.ts`: `JOBS_LOAD_ERROR_PREFIX`와 `jobsLoadErrorText(err)`.
  기존 "작업 상태 조회 실패" 문구를 유지한다.

### 3. `shared/components/SegToggle.tsx`

`PlanPanel.tsx:17-36`과 `OverviewEditor.tsx:9-28`의 동일 컴포넌트를 추출한다.
props·클래스(`plan-seg*`)·동작을 동일하게 유지하고 두 파일에서 import한다.

### 4. `shared/lib/jobs.ts` predicate

```ts
export function isRunning(j: Job): boolean;
export function isQueued(j: Job): boolean;
export function isActive(j: Job): boolean;
export function isJobTypeActive(jobs: Job[], types: string[]): boolean;
```

- 기존 `hasActive`/`latestActive`는 유지하고 내부에서 predicate를 재사용한다.
- `useReviews`의 `hasReviewActive`, `ReviewPanel`의 상태 판정을 대체한다.
- **`refetchInterval` 소유자는 `useActiveJobs` 하나만 유지**한다(ADR 15).

### 5. 로딩 표시

`OutputsPanel.tsx:59`, `ReviewPanel.tsx:21`의 `<Empty>불러오는 중…</Empty>`를
기존 `<Loading />`으로 교체한다. 로딩 문구 자체는 동일.

### 6. 레이어 역전 해소

`useOverview.ts:5`의 `fmtBytes` import를 `shared/lib/format`으로 바꾼다.
`ui.tsx` 재수출 덕분에 다른 파일은 수정하지 않아도 된다.

### 7. 테스트/검증

프론트 단위 테스트 러너는 없다. `npm run build`(tsc --noEmit + vite build)가 유일한
게이트다. 새 테스트 러너를 도입하지 않는다.

## Acceptance Criteria

```powershell
npm --prefix frontend run build
```

## 검증 절차

1. AC를 실행한다.
2. 체크리스트:
   - query key·invalidation·fetch 경로가 바뀌지 않았는가?
   - 사용자 문구가 동일한가(로딩 표시 교체 제외)?
   - CSS 클래스 이름이 동일한가?
   - 토큰(`tokens.css`)을 건드리지 않았는가?
3. `phases/refactor-standalone-cli/index.json`의 step 10을 갱신한다.

## 금지사항

- `fetchPlans` 통합·queryKey 팩토리·교차 feature 데이터 중복 제거를 하지 마라. 이유:
  캐시 식별자/무효화 동작이 바뀌어 조용한 리페치 변경이 생긴다(유예).
- `useActiveJobs` 외에 `refetchInterval`을 추가하지 마라. 이유: ADR 결정 15.
- 디자인 토큰을 변경하지 마라. 이유: 원칙 7의 4종 세트 절차가 필요하다.
- View에 fetch/서버 데이터 로직을 추가하지 마라. 이유: MVVM 계약 위반.
