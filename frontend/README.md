# frontend — PlanForge 웹 UI

React 19 + TypeScript + Vite 6로 만든 SPA다. **의존성 최소**가 설계 원칙(요청서 §3.1)이라
라우터·상태관리·UI 컴포넌트 라이브러리 없이 — 자체 해시 라우터, 플레인 훅 상태,
플레인 CSS 8파일로 구성되어 있다. 아이콘은 `lucide-react`만 허용된다.

사용자 관점 사용법은 루트 [README.md §5](../README.md#5-웹-ui-사용-방법-단계별),
설치·기동은 [§4](../README.md#4-개발-환경-설정-수동-실행)를 참고한다.

```
[브라우저] ── 동일 오리진 /api ──► [Vite dev 프록시 | nginx] ──► [FastAPI :8000]
```

## 디렉터리 구조

```
frontend/
├── index.html                  lang="ko" · <title>PlanForge</title>
├── vite.config.ts              /api → localhost:8000 프록시 + SSE 버퍼링 방지
├── tsconfig.json               strict + noUncheckedIndexedAccess · noEmit
├── openapi.json                백엔드에서 덤프한 OpenAPI 스키마 (커밋됨 — 계약 원료)
├── package.json
├── Dockerfile                  node:22-alpine 빌드 → nginx:1.27-alpine 서빙
├── nginx.conf                  배포판 /api 프록시(proxy_buffering off) + SPA fallback
├── e2e-smoke.mjs               브라우저 e2e 수동 스모크 (실제 LLM · 커밋 대상 아님)
├── visual-smoke.mjs            리스타일 스크린샷 스모크 (LLM 호출 없음)
└── src/
    ├── main.tsx                엔트리 — CSS 8개 import 순서 고정 + <App/>
    ├── App.tsx                 앱 셸: 스티키 헤더 + 해시 라우팅 분기 + 탭 키
    ├── api/
    │   ├── client.ts           REST 래퍼 + SSE 파서 + 계약 타입 재수출
    │   └── types.gen.ts        openapi-typescript 생성물 (자동 생성 — 직접 수정 금지)
    ├── components/
    │   ├── ui.tsx              Button/Banner/Loading/Empty/PageHeader + fmtBytes/fmtDateTime
    │   ├── CmEditor.tsx        CodeMirror 6 래퍼 (CmEditor · CmDiff)
    │   ├── MarkdownPreview.tsx marked → DOMPurify 소독 미리보기
    │   └── HeaderMetrics.tsx   헤더 메트릭 필 (plan SSOT/확립 팩트/최근 검수)
    ├── lib/
    │   └── hashRoute.ts        의존성 없는 해시 라우터 (useHashRoute/navigate/routeParam)
    ├── pages/
    │   ├── ProjectsPage.tsx    프로젝트 목록 + 생성·삭제 모달
    │   ├── ProjectPage.tsx     프로젝트 셸 — 5탭 + 배지
    │   ├── SourcesPanel.tsx    소스 문서 업로드/삭제
    │   ├── InterviewPanel.tsx  인터뷰 채팅 + SSE + 게이트 (최대 파일)
    │   ├── PlanPanel.tsx       plan.md 뷰어/편집/diff/승인
    │   ├── OutputsPanel.tsx    파생물 갤러리 + job 폴링
    │   └── ReviewPanel.tsx     검수 리포트 + plan 반영
    └── styles/
        ├── tokens.css          theme.py 미러 디자인 토큰 (+ 화면 전용 토큰)
        └── base/app/pages/chat/plan/outputs/review.css
```

## 스크립트

| 스크립트 | 동작 |
|---|---|
| `npm run dev` | Vite 개발 서버(기본 포트 5173) + `/api` → `http://localhost:8000` 프록시 |
| `npm run build` | **`tsc --noEmit && vite build`** — 타입체크를 빌드 앞에 강제(미통과 시 빌드 실패). 산출물 `dist/` |
| `npm run preview` | 빌드 결과 로컬 확인 |
| `npm run gen:types` | `openapi-typescript ./openapi.json -o src/api/types.gen.ts` — 계약 타입 재생성 |

lint 설정은 없다. 타입 안전성은 `tsc --noEmit`(build에 포함)이 담당한다.

## 의존성

| 패키지 | 역할 |
|---|---|
| `react` / `react-dom` ^19 | UI (리액트 외 라이브러리 상태관리·라우팅 전무) |
| `codemirror` ^6 (+`state`/`view`/`lang-markdown`/`merge`) | plan.md 에디터(CmEditor)와 diff(CmDiff — MergeView) |
| `marked` ^15 | 마크다운 → HTML |
| `dompurify` ^3.2 | 미리보기 HTML XSS 소독 |
| `lucide-react` | 아이콘 (허용된 유일 아이콘 라이브러리) |
| `vite` ^6 / `@vitejs/plugin-react` / `typescript` ~5.7 | 빌드·타입체크 |
| `openapi-typescript` ^7 | `gen:types` — 백엔드 계약 타입 생성 |
| `playwright` ^1.63 | 스모크 스크립트(chromium) 전용 |

## 라우팅 (해시 라우터)

react-router 없이 `lib/hashRoute.ts`의 `hashchange` 기반 3개 라우트만 있다:

| 라우트 | 화면 |
|---|---|
| `#/` | 프로젝트 목록 |
| `#/projects/:id` | → `#/projects/:id/interview`로 치환 (ProjectRedirect) |
| `#/projects/:id/:tab` | 탭 — `interview · plan · outputs · review · sources` |

설정 화면은 없다 — LLM 설정은 백엔드 `backend/planforge/config.json` 소관이다.

`App.tsx`는 스티키 헤더(브랜드 + `/api/health` 폴링 "API 연결됨/안 됨" 배지 +
프로젝트 라우트에서만 `HeaderMetrics`)를 렌더한다.

## API 클라이언트 & 타입 계약 (`src/api/`)

계약 잠금 파이프라인(요청서 §3.1) — 백엔드 API 스키마가 바뀌면 반드시 2단계 재생성:

```
① backend/ 에서  python scripts/export_openapi.py   →  frontend/openapi.json 덤프
② frontend/ 에서 npm run gen:types                  →  src/api/types.gen.ts 재생성
```

- `types.gen.ts`는 자동 생성물 — 직접 수정 금지.
- 앱 코드는 `client.ts`가 재수출한 타입(`Project · Job · Fact · Plan · Derivative ·
  Build · Review · ReviewFinding · SourceFile · Session · CompactPreview ·
  CompactApplyResult · Message`)으로만 소비한다.
- `api()` 공통 fetch 래퍼(`ApiError`가 status + FastAPI `detail`을 파싱)와
  `apiGet/apiPost/apiDelete/apiUpload`(multipart)를 제공한다.

### SSE (인터뷰 턴)

- **EventSource 미사용** — EventSource는 GET만 지원하지만 인터뷰 턴 계약(설계 D6)은
  "POST의 응답이 곧 SSE 스트림"이므로 `fetch` + `ReadableStream`을 직접 파싱한다
  (`client.ts`의 `apiSSE` / `parseSSE` — `\n\n` 프레임에서 `event:`/`data:` 분해).
- 이벤트: `token`(스트리밍 텍스트 누적) · `error` · 카드/상태 이벤트. 카드 이벤트는
  done 후 세션·메시지 전체 리로드로 정리한다("이력이 권위" — 서버 데이터가 SSOT).
- 백엔드 대응물은 `backend/app/events.py`의 `Event(name, payload)`.
- 프록시도 스트림을 통과해야 하므로 `vite.config.ts`가 응답에
  `x-accel-buffering: no`를 강제하고, 배포 nginx도 `proxy_buffering off`를 유지한다.

## 패널 가이드 (`src/pages/`)

| 패널 | 내용 |
|---|---|
| `ProjectsPage` | 목록. 생성 모달(슬러그 `^[a-z0-9][a-z0-9-]*$`, ≤64자 — 백엔드와 동일 검증), 삭제 확인 팝업은 **프로젝트 제목을 정확히 타이핑해야 활성화**. |
| `ProjectPage` | 셸 — 탭 순서: 소스 → 인터뷰 → 계획정의(plan.md) → 산출물 → 검수. `useTabBadges`가 마운트 1회 `Promise.allSettled`로 카운트 배지 수집(plan 배지는 `vNN`만 — D9). |
| `SourcesPanel` | 프로젝트 소스(업로드/삭제) + 글로벌 소스(읽기 전용). `.md .txt .json .csv`, 2MB. `data-testid="source-file-input"`은 e2e 셀렉터 계약. |
| `InterviewPanel` | 인터뷰 채팅. **모든 진행이 `run()` 한 경로** = POST → SSE 소비(D6). 페이즈: `hypothesis → awaiting_answers → fact_gate → key_message_gate → plan_review → approved/failed`. 카드: `AnswersCard`(선택지 답변) · `FactGate`(수정 가능 승인/반려) · `KeyGate`(핵심 메시지 3개) · `CompactCard`(팩트 압축). 우측 `FactSidePanel`은 조회 전용 — 팩트 확립은 게이트에서만(원칙 4 게이트 우회 금지). 세션 id는 `localStorage["pf-session-<pid>"]` 보관(서버 데이터가 권위). |
| `PlanPanel` | 세대 리스트 + 툴바(보기/편집/이전 세대 대비). 토글: 보기·diff 모드는 `코드\|뷰어`, 편집 모드는 `코드\|분할\|뷰어`. 저장은 항상 `POST /plans/{id}/revise`로 **새 세대 DRAFT** 생성(덮어쓰기 없음), 승인은 draft일 때만 `POST /plans/{id}/approve`. 에디터 `CmEditor` · diff `CmDiff`(CodeMirror MergeView) · 미리보기 `MarkdownPreview`. |
| `OutputsPanel` | 승인 plan 필요. "PPT 생성(slides)" / "문서 생성(MD·HTML·DOCX)" → job 큐잉(202) → **1.5초 폴링**. 미리보기: md는 fetch 후 렌더, html은 iframe, pptx/docx는 다운로드. 채번 `문서제목_vNN.확장자` 절대 덮어쓰기 금지(원칙 5). job 목록에 유형(`derive_build/review/plan_revise`)·오류분류 표시. |
| `ReviewPanel` | "검수 실행" → job 폴링 → 리포트 목록(🔴/🟡/⚪ 카운트) → 상세에서 **발견사항 체크박스 선택 → `POST /api/plans/{id}/revise-from-review`**로 plan 새 세대 생성(FR-4.3 SSOT 게이트). |

### 상태 관리 · 폴링

react-query·zustand·redux 전무 — 전부 로컬 훅 상태(`useState`/`useEffect`/`useRef`)와
fetch. job 진행은 `setInterval(1500)` 폴링(`pollRef`로 정리), 헤더 메트릭은 10초 폴링,
탭 배지는 마운트 1회다.

## 스타일링 & 디자인 토큰

- **플레인 CSS 8파일**(`src/styles/`) — CSS 모듈·Tailwind·CSS-in-JS 없음.
  `main.tsx`의 import 순서(`tokens → base → app → pages → chat → plan → outputs →
  review`)로 레이어화한다. 다크 모드는 없다(라이트 단일 테마).
- `tokens.css`는 2개 `:root` 블록으로 구성:
  1. **theme.py 미러** — 색 `--navy/--blue/--light-blue/--bg/--bg-soft/--text/...`,
     폰트 `"Malgun Gothic"`, 크기 4단(`--fs-title:28px ← SIZE_SLIDE_TITLE`),
     `--margin:24px ← MARGIN 0.6in`.
  2. **화면 전용 토큰**(미러 아님) — surface/shadow/space/radius/`--header-h`/`--container`.
- **토큰 4종 세트 계약(원칙 7)**: SSOT는 `backend/planforge/builders/theme.py`이며
  theme.py(권위) · 빌더 리터럴 · `tests/fixtures` · `frontend/tokens.css`를 **동시
  점검·수정**해야 한다. 절차는 `docs/token-checklist.md` — 하나만 고치는 PR은 반려된다.
- 반응형은 미디어쿼리(768/1024/800/480px 등)로 처리한다.

## 스모크 스크립트

### `e2e-smoke.mjs` — 브라우저 e2e (수동, 커밋 대상 아님)

전제: backend(:8000) + frontend dev(:5173) 기동 + **실제 LLM**. playwright chromium
으로 풀 시나리오를 돌린다(소요 수 분 — kick 300s · 답변 600s · 빌드 1,200s 대기).

```
① 프로젝트 생성(고유 슬러그) → ② 소스 업로드 → ③ 인터뷰 kick → 게이트 루프(최대 8회)
→ ④ plan 승인 → ⑤ 산출물 PPT+문서 생성(갤러리 ≥4행 대기) → ⑥ 검수 실행 → 발견사항 조회
```

- 콘솔/페이지 에러를 수집하고 하나라도 있으면 exit 2.
- 스크린샷은 저장소 루트 `.e2e-shots/`에 쌓인다(gitignore 대상 — 커밋 금지).
- 이 파일 자체도 `.gitignore`에 명시되어 있다 — 로컬 수동 검증용.

### `visual-smoke.mjs` — 리스타일 확인 (커밋됨, 임시)

LLM 호출 없음(인터뷰 세션만 생성, kick 안 함). 홈 + 특정 프로젝트(pid 하드코딩)의
5탭을 fullPage 캡처해 `.e2e-shots/restyle/`에 저장한다. 본 e2e 전 빠른 눈확인용.

## 기타 개발 정보

- **환경변수**: `VITE_*` 사용처가 없다. API는 전부 동일 오리진 `/api` 경로로 호출한다
  (dev는 Vite 프록시, 배포는 nginx 프록시가 같은 역할).
- **tsconfig**: `strict` + `noUnusedLocals/Parameters` + `noUncheckedIndexedAccess`
  + `verbatimModuleSyntax` + `noEmit`. 빌드는 `tsc --noEmit`(체크)과 `vite build`
  (산출물) 2단계다.
- **Docker**: `Dockerfile`은 node:22-alpine에서 빌드 후 nginx:1.27-alpine으로 서빙.
  `nginx.conf`가 `/api/` → `http://backend:8000`(버퍼링 off, read timeout 3600s)과
  해시 라우팅용 SPA fallback(`try_files $uri /index.html`)을 담당한다.
- **e2e 셀렉터 계약**: 일부 요소는 스모크 스크립트와 암묵 계약이 있다 —
  소스 업로드 `data-testid="source-file-input"`, 헤더 메트릭(`HeaderMetrics`)은
  의도적으로 div만 렌더해 `button:has-text('승인')` 셀렉터 오염을 막는다(D9).
  이 셀렉터를 건드리는 UI 변경은 스모크를 깬다.

## 개발 시 주의사항

- API 스키마를 바꿨다면 **2단계 타입 재생성**(`export_openapi.py` → `gen:types`)을
  반드시 돌린다 — `types.gen.ts`를 손으로 고치지 않는다.
- 인터뷰 턴 추가/변경 시 **POST=SSE 계약(D6)** 을 유지한다(새 EventSource GET 금지).
- plan 데이터의 유일 원본은 백엔드 DB(`plans.markdown`)다. 프론트는 plan을 고치면
  항상 revise API로 새 세대를 만들고, 직접 덮어쓰는 경로를 만들지 않는다(SSOT).
- 디자인 토큰 변경은 `docs/token-checklist.md` 절차(4종 세트 동시 수정)를 따른다.
- 아이콘은 lucide-react만, 새 UI 라이브러리 도입은 금지(의존성 최소 원칙).