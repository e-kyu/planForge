# Step 7: contract-types

## 읽어야 할 파일

먼저 아래 파일들을 읽어라:

- `/CLAUDE.md` — 계약 갱신 흐름(OpenAPI → types.gen.ts)·가상환경 계약
- `/docs/ARCHITECTURE.md` — API 계약 섹션
- `/backend/scripts/export_openapi.py` — 생성 방식 (backend venv python 사용이 계약)
- `/frontend/package.json` — `gen:types`·`build` 스크립트
- `/frontend/src/api/types.gen.ts` — 자동 생성물 (수정 금지, 갱신 대상)
- `phases/doc-loop/step{0..6}-output.json` — 지금까지의 계약 변경 요약

## 작업

step 0~6 동안 누적된 백엔드 API 계약 변경(doc_loops 엔드포인트·doc_slug 필드들)을
프론트엔드 생성 타입에 반영하고, 타입 체크가 통과하는지 확인한다.

이 step은 **새 기능 코드를 쓰지 않는다** — 계약 동기화 + 타입 체크 게이트만.

### 1. 계약 재export

backend 가상환경(`backend/.venv`)을 사용한다 (시스템 python 금지 — 커밋 계약):

```powershell
# backend/ 에서 (가상환경 활성)
python scripts/export_openapi.py
```

생성된 `frontend/openapi.json`의 `git diff`를 확인한다. 기대 변경:

- `docloops` 태그의 `GET /api/projects/{project_id}/docloops` 신설
- `ProjectOut`에 `docloops` 내장
- `PlanOut`·`SessionOut`·`SessionCreate`·`DerivativeCreate`에 `doc_slug`
- `BuildOut`에 `doc_slug`, outputs 목록에 `doc_slug` query 파라미터
- `list_plans`에 `doc_slug` query 파라미터

diff에 기대 밖 변경(필드 삭제·이름 변경)이 있으면 step 0~6에서 실수한 것이므로
수정 전 되돌려 검토하라.

### 2. 타입 갱신

```powershell
# frontend/ 에서
npm run gen:types
```

### 3. 타입 체크

```powershell
npm run build   # tsc --noEmit 포함
```

기존 코드가 doc_slug 없이 타입을 쓰는 경우(optional 필드 추가라 무수정 통과가
원칙이다) 빌드가 깨진다면, 타입이 breaking인 곳만 최소 수정한다. 새 UI 코드는
step 8·9에서 쓰므로 이 step에서 화면 로직을 추가하지 않는다.

### 4. 커밋 대상 확인

`frontend/openapi.json`·`frontend/src/api/types.gen.ts`는 커밋 대상 자동생성물이다.
최종 `git status`에서 이 둘이 변경됐고 그 외 계약 무관 잡음(openapi.json을
ripgrep 제외했어도 git에는 잡힘)이 없는지 확인한다.

## Acceptance Criteria

```powershell
# backend/ (venv) 후 frontend/ 에서 순차 실행
python scripts/export_openapi.py
npm run gen:types
npm run build
```

`npm run build`가 tsc --noEmit 포함해 실패 없이 통과해야 한다.

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `git diff --stat`로 변경 파일이 계약 2종(openapi.json·types.gen.ts) + 기존 코드의
   최소 호환 수정에 한정되는지 확인한다.
3. 결과에 따라 `/phases/doc-loop/index.json`의 해당 step을 업데이트한다
   (completed + summary — step 8에서 쓸 DocLoopOut·doc_slug 타입 이름을 명시).

## 금지사항

- `frontend/src/api/types.gen.ts`를 손으로 편집하는 것 금지 — 이유: 자동 생성물이고
  손편집은 다음 gen:types에서 유실된다.
- 시스템 python으로 export_openapi를 돌리는 것 금지 — 이유: venv 외 환경은 계약
  스키마가 다를 수 있다(backend CLAUDE.md 계약).
- 이 step에서 새 UI·로직 코드를 작성하는 것 금지 — 이유: scope 최소화. 화면 작업은
  step 8·9다.
- `npm install`로 의존성을 추가하는 것 금지 — 이유: 이 기능은 새 의존성을 요구하지
  않는다.