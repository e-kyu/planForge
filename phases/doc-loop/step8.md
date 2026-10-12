# Step 8: doc-routing

## 읽어야 할 파일

먼저 아래 파일들을 읽어라:

- `/CLAUDE.md` — 프론트엔드 구조(feature-MVVM·View에 fetch 금지§4.3) 계약
- `/docs/ARCHITECTURE.md` — §2 프론트엔드 feature-MVVM
- `/frontend/src/App.tsx` — hash 라우팅 (`#/projects/:pid/:tab` 해석부)
- `/frontend/src/features/projects/views/ProjectsPage.tsx` — 카드 (버튼은 step 9)
- `/frontend/src/features/projects/models/projectApi.ts`(및 projects feature의
  models/·viewmodels/ 전체) — fetchProjects·프로젝트 상태 훅. `DocLoopOut` 타입은
  step 7에서 types.gen.ts로 생성돼 있다.
- 인터뷰 feature: `frontend/src/features/interview/` 전체 — 특히 viewmodels의
  세션 훅(localStorage 키 `pf-session-{pid}` 사용부)과 models의 createSession
- plan/출력 패널: plan·outputs feature의 viewmodels(models)의 `fetchPlans`·
  outputs fetch — `?doc_slug=` 전달 위치
- `/frontend/src/features/project/views/ProjectPage.tsx` (실제 파일명/위치를
  먼저 확인하고 이 문서의 표기를 실제 경로로 치환해 진행) — doc 칩 행 추가 위치

`phases/doc-loop/step7-output.json` — DocLoopOut·doc_slug 계약 타입 요약.

## 작업

라우팅과 데이터 훅 계층에 "문서(doc)" 차원을 추가한다. 이 step은 라우트 해석·
훅 파라미터·패널 props의 배관(plumbing)이고, **버튼 UI는 step 9**다.

### 1. doc 슬러그 상수 — `frontend/src/features/projects/models/`

```typescript
/** 문서 루프 슬러그 — 백엔드 docloops DOC_KINDS와 동기 (SSOT는 백엔드) */
export const DOC_SLUGS = ["proposal", "uiux-design", "dev-design"] as const;
export type DocSlug = (typeof DOC_SLUGS)[number];
```

### 2. 라우팅 — `frontend/src/App.tsx`

현행 `#/projects/:pid/:tab` 해석을 확장한다:

- `#/projects/:pid/:seg3` — seg3가 기존 탭 키면 **레거시 라우트 그대로** (doc=null).
- `#/projects/:pid/:docSlug/:tab` — seg3가 DOC_SLUGS 원소면 doc=그 slug로 해석,
  tab은 기존 탭 키. docSlug가 DOC_SLUGS 밖 단어면 기존 탭 해석 유지(레거시 우선 —
  기존 탭 키와 DOC_SLUGS가 겹치지 않으므로 충돌 없음).
- 렌더링은 기존 페이지 컴포넌트에 `doc?: DocSlug` prop 추가 전달.

### 3. ProjectPage — doc 칩 행

- `doc` prop 수신 (+ `docloops: DocLoopOut[]` — 프로젝트 응답에서).
- `docloops`가 빈 배열이면(레거시 프로젝트) 칩 행을 렌더링하지 않는다 — 기존 화면
  그대로.
- 칩 행: 3개 문서 칩(proposal·uiux-design·dev-design) — 라벨은 응답의 `label`
  필드를 그대로 사용. 칩 상태 표기: status 그대로 (locked/active/done — 스타일은
  step 9와 톤 통일, 이 step에서는 표시만). 현재 doc 칩은 강조.
  칩 클릭 → `#/projects/{pid}/{slug}/{현재탭}` 이동.
- doc 라우트로 진입했는데 해당 문서의 상태가 locked면 인터뷰 탭은 세션 생성 대신
  locked 안내만 보여준다(표시 수준 — 게이트 409는 백엔드도 막지만 UX로 1차 안내).
- doc 미지정(레거시) 라우트로 진입했는데 프로젝트에 docloops가 있으면 doc=현재
  active 문서로 리다이렉트(전부 done이면 마지막 문서) — 이유: 문서 루프 프로젝트에
  레거시 탭 UI("전체 plan")가 보이면 사용자가 두 SSOT 흐름을 혼동한다. 레거시
  프로젝트(docloops=[])는 그대로.

### 4. 훅·패널 doc 전달 — feature 계층 경유 원칙 (View fetch 금지)

- 인터뷰 세션 훅: `useInterview(pid, doc | null)` 형태로 파라미터 확장.
  localStorage 키: doc가 있으면 `pf-session-{pid}-{doc}`, 없으면 기존 키
  `pf-session-{pid}` **그대로** (기존 사용자 세션 보존). 세션 생성 호출도
  `createSession(pid, doc_slug)` 확장.
- plan 패널 훅: plan 목록 fetch에 `?doc_slug=` 파라미터 전달 (doc 있는 라우트에서만).
- 출력 패널 훅: outputs fetch·다운로드에 동일 전달.
- 패널 컴포넌트(PlanPanel·OutputsPanel 등)는 viewmodel 훅 경유로 doc을 받는다 —
  **View에서 fetch 금지 계약** (가이드 §4.3).
- SSE 턴·도구 계약 등 인터뷰 로직은 변경 없음 — 세션 식별자만 doc별로 분리된다.

### 5. 테스트

기존 `npm run build`(tsc 포함) 통과가 AC다. 프론트 단위 테스트 인프라가 없으므로
신규 라우트는 AC 커맨드 + step 9의 UI와 함께 최종 회귀에서 확인한다. 이 step에서
수동 확인할 사항(개발 서버 2개 기동 후):

- 레거시 라우트(docloops=[] 프로젝트) 화면 동작이 기존과 동일
- doc 라우트 파싱: `#/projects/1/proposal/plan` 식 입력이 올바르게 해석됨
- localStorage 키 분리(`pf-session-1` vs `pf-session-1-proposal`)

## Acceptance Criteria

```powershell
npm run build    # frontend/에서 — tsc --noEmit 포함
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트:
   - 모든 fetch가 viewmodels/models 훅 경유인가? (View에 직접 fetch 금지)
   - 라우트 해석에서 레거시 경로가 무손상인가? (기존 탭 키로의 회귀 확인)
   - `DocSlug` 상수가 백엔드 DOC_KINDS 순서·철자와 일치하는가?
3. 결과에 따라 `/phases/doc-loop/index.json`의 해당 step을 업데이트한다
   (completed + summary — 새 라우트 형식·훅 시그니처를 step 9가 이어받도록 명시).

## 금지사항

- `types.gen.ts` 손편지 금지 — 이유: 자동 생성물(step 7 계약).
- 버튼 UI를 ProjectsPage에 추가하는 것 금지 — 이유: scope 분할. step 9가 담당한다.
- localStorage 기존 키(`pf-session-{pid}`)를 새 키로 마이그레이션·삭제하는 것 금지 —
  이유: 레거시 프로젝트·진행 중 세션의 사용자 데이터 보존 계약.
- View 컴포넌트에서 직접 fetch/서버 상태 로직 금지 — 이유: feature-MVVM §4.3 계약.
- 인터뷰 SSE·턴 도구 계약 변경 금지 — 이유: 백엔드 계약 4세트(INTERVIEW-TURN-
  CONTRACT)는 이 step에서 이미 확정 상태이고 프론트는 소비자다.
- 배지·메트릭(useProjectShell 등)의 집계를 문서별로 분리하는 것 금지 — 이유: Phase 1
  확정 범위는 전체 집계 유지이며 세분화는 Phase 2다.