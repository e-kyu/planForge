# Step 1: outputs-request-slug — 산출물 생성 요청에 루프 doc_slug 실어 보내기 (프론트)

## 배경 (자기완결 — 외부 대화 참조 금지)

이전 step(derive-doc-slug-guard)에서 백엔드 `POST /api/projects/{pid}/derivatives`가
doc-loop 프로젝트의 doc_slug 누락을 409로 거부하게 됐다(미상 slug는 404). 이제 프론트가
생성 요청에 라우트의 루프 slug를 `doc_slug`로 실어 보내야 실질 버그가 해소된다.

실버그:

두 문서 루프 done 상태에서 제안서 탭의 산출물 생성이 UI·UX plan으로 기록됐던 원인은
프론트가 doc_slug를 전혀 보내지 않아서였다.

`OutputsPanel`에는 정의가 다른 doc 개념이 두 개 있다:
- **prop `doc`** — 루프 slug(`DocSlug` — proposal/uiux-design/dev-design). 라우트에 연동한
  문서 스코프 식별자 (`useOutputs(pid, doc)`의 첫인자 — 이미 조회 계열(?doc_slug=)에 쓰임).
 - **로컬 상태 `docSel`** — plan 본문 `- 산출 문서:` 라인의 한글 유형 라벨(제안서
  ·UI·UX설계서 등, `plan.docs` 파생). 슬라이드 생성 시 어떤 문서유형을 만들지 지정하는
  `body.doc` 값이다.

이 step은 두 개념의 이름을 분해하고, body에 루프 slug를 넣어 보낸다.

## 읽아야 할 파일

- `/CLAUDE.md`, `/frontend/CLAUDE.md` — view에서 fetch 금지(모델→viewmodel 경유) 규칙
- 이전 step의 `backend/app/modules/derivatives/presentation/api.py` — 새 가드(409/404) 확인
- `/frontend/src/features/outputs/models/outputsApi.ts` — 주 대상 1
- `/frontend/src/features/outputs/viewmodels/useOutputs.ts` — 주 대상 2
- `/frontend/src/features/outputs/views/OutputsPanel.tsx` — 주 대상 3 (표현 계층)
- `/frontend/src/features/interview/models/interviewApi.ts` — createSession이 body에
  doc_slug를 실어 보내는 기존 패턴(참고)
- `/frontend/src/features/projects/models/docloops.ts` — `DocSlug` 타입 출처

## 작업

### 1. `frontend/src/features/outputs/models/outputsApi.ts`

`enqueueDerivative` body 타입에 `doc_slug` 추가:

```ts
import type { DocSlug } from "../../projects/models/docloops";

export const enqueueDerivative = (
  pid: number,
  body: { kind: "slides" | "report"; doc_slug?: DocSlug; doc?: string; fmts?: string[] },
) => apiPost<Job>(`/api/projects/${pid}/derivatives`, body);
```

### 2. `frontend/src/features/outputs/viewmodels/useOutputs.ts`

- `enqueueM.mutationFn`의 body 타입에 `doc_slug?: DocSlug` 허용.
- `enqueue` 함수 시그니처: 두 번째 인자명을 `docLabel`(plan 문서유형 라벨)로 바꿔
  훅 파라미터 `doc`(루트 DocSlug)과 섞이지 않게 한다:

```ts
function enqueue(kind: "slides" | "report", docLabel: string | undefined, fmts?: string[]) {
  // ... 기존 setError/setNotice/setPending 로직 유지
  enqueueM.mutate({ kind, doc: docLabel, fmts, doc_slug: doc ?? undefined });
}
```

- **`doc ?? undefined`가 핵심**: doc(루프 slug)이 null인 레거시 라우트는 이전 와이어
  포맷을 그대로 유지(doc_slug 키 미전달) — 백엔드 가드의 레거시 허용 계약과 짝이 된다.
- 훅 파라미터 `doc`과 `docLabel`의 개념 차이(루트 slug vs plan 본문 라벨)를
  주석으로 남긴다.

### 3. `frontend/src/features/outputs/views/OutputsPanel.tsx`

- `docSel`(로컬 상태)을 `docLabelSel`로 rename하고 prop `doc`(루트 slug)과의 구분을
  주석으로 남긴다.
- 생성 버튼 호출부는 `enqueue("slides", docLabelSel || undefined)` 등 **형태를 유지**한다
  — doc_slug는 viewmodel이 자기 소유 doc에서 채운다. View에서 fetch·서버 로직을
  직접 다루지 않는다(§4.3 계약).
- OutputsPanel의 prop 계약(`{pid, doc}`)과 ProjectPage의 호출부는 무변경.

## Acceptance Criteria

```bash
cd frontend && npm run build          # tsc --noEmit 포함
git diff --exit-code -- src/api/types.gen.ts   # 타입 생성물 무변경 (프로젝트 루트에서)
```

## 검증 절차

1. 위 AC 커맨드를 실행해 통과를 확인한다. types.gen.ts가 바뀌었다면 이유를 재점검한다
   (doc_slug는 types.gen.ts에 이미 있고 body 타입은 모델 계층의 자체 타입이라
   변경 불필요가 정답이다).
2. 아키텍처 체크리스트:
   - View에서 fetch·서버 데이터 로직을 직접 다루지 않았는가? (모델→viewmodel 경유)
   - prop 계약 변경이나 다른 feature에 대한 영향이 없는가?
   - `frontend/CLAUDE.md` 규칙 위반 없는가?
3. 최종 회귀 검사로 프로젝트 루트에서 `python -m pytest -q` 전체 실행(다른 계층의
   회귀 가림) — 이건 step 0이 이미 다 통과시킨 기반이다.
4. `phases/derive-doc-slug/index.json`의 step 1 status를 업데이트한다
   (성공 → `"completed"` + `"summary"` 한 줄).

## 금지사항

- `src/api/types.gen.ts`를 손수 편집하거나 `npm run gen:types`/backend export 스크립트를
  실행하지 마라 — 이유: 이번 변경은 OpenAPI 스키마 불변(가드는 런타임 에러)이고
  생성물 편집은 계약 위반이다.
- `OutputsPanel.tsx`의 prop 계약(`{pid, doc}`)과 ProjectPage 호출부를 바꾸지 마라 —
  이유: 라우팅·조회 계열은 이미 정상이고 이번 결함은 생성 요청 파라미터 누락이다.
- 레거시 라우트(doc=null)의 와이어 포맷을 강제로 doc_slug 누락에서 벗어나게 하지 마라 —
  - 이유: 백엔드 가드(이전 step)의 레거시 허용 계약과 짝을 맞춰야 한다 (doc ?? undefined).
- 기존 테스트를 깨뜨리지 마라.