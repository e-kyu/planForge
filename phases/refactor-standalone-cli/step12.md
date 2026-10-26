# Step 12: docs-and-verification

## 읽어야 할 파일

- `/CLAUDE.md`, `/backend/CLAUDE.md`, `/frontend/CLAUDE.md`
- `/docs/ARCHITECTURE.md`, `/docs/ADR.md`, `/docs/UI_GUIDE.md`, `/docs/PRD.md`
- `/docs/INTERVIEW-TURN-CONTRACT.md`
- `/README.md`, `/backend/README.md`, `/frontend/README.md`
- `/packages/planforge-cli/README.md`, `/packages/planforge-cli/pyproject.toml`
- `/phases/refactor-standalone-cli/index.json` — 이전 step summary 전체

## 배경

Step 0~11에서 구조·공통 커널·CLI·백엔드/프론트 리팩토링을 완료했다. 이 step은 새
구조를 문서에 반영하고, 전체 검증을 실행해 동작 불변을 확정한다.

## 작업

### 1. 문서 갱신

- `CLAUDE.md`:
  - 구조 절에 `packages/planforge-cli/`(독립 패키지), `planforge/common`, `planforge/cli`,
    `backend/scripts/admin.py`를 반영.
  - 명령어 절에 `planforge ...`, `python -m planforge ...`,
    `python backend/scripts/admin.py openapi|job-timing`,
    `pip install -e packages/planforge-cli`를 추가.
  - 설계 원칙 계약 8개는 문구·의미를 바꾸지 않는다.
  - "변경 금지"에 빌더 경로가 새 위치로 표기되게 한다(내용 불변).
- `backend/CLAUDE.md`: 구조·CLI·테스트 절의 경로 갱신. `planforge/`가 외부 패키지임을
  명시.
- `docs/ARCHITECTURE.md`: 디렉토리 트리와 의존 방향(`backend/app → packages/planforge-cli`) 갱신.
- `docs/ADR.md`: 새 결정 항목(예: 23) 추가 —
  - 독립 배포 패키지 추출 배경·형태·설치/Docker 변경.
  - 동작 불변 원칙과 계약(OpenAPI/SSE/문자열) 유지.
  - 유예 항목(D5·D10·D12·D14·D16·D17·D18·D20·D22·D24·D25·D28, 프론트 queryKey/캐시
    중복, lint)과 이유.
  - `backend/planforge/config.json` 런타임 설정 경로 보존.
- `docs/UI_GUIDE.md`: `planforge/builders/...` 경로를 새 패키지 경로로 갱신. 토큰 값·
  절차는 불변.
- `docs/PRD.md`: 구조상 `theme.py` 경로 언급이 있으면 갱신.
- `docs/INTERVIEW-TURN-CONTRACT.md`: 경로가 실제로 바뀐 경우에만 갱신(도구 스키마·
  프롬프트 계약은 불변).
- `README.md`, `backend/README.md`, `frontend/README.md`: 디렉토리 구조·CLI·테스트
  명령 갱신. 루트 README의 모듈 수(9종)와 docloops 누락도 이번에 정합화.
- `packages/planforge-cli/README.md`: 설치·`planforge` 명령·`python -m planforge`
  호환·`backend/` 실행 위치·설정 경로를 최종 확인.

### 2. phase 상태

`phases/refactor-standalone-cli/index.json`의 step 12를 완료로 갱신한다.
`phases/index.json`의 task 상태는 execute.py가 자동 갱신한다.

### 3. 최종 검증

아래를 모두 실행한다.

```powershell
backend\.venv\Scripts\python.exe -m pytest
backend\.venv\Scripts\python.exe -m pytest scripts\test_execute.py -q
backend\.venv\Scripts\python.exe backend\scripts\export_openapi.py
git diff --exit-code -- frontend/openapi.json
npm --prefix frontend run build
backend\.venv\Scripts\python.exe -m planforge --help
backend\.venv\Scripts\python.exe backend\scripts\admin.py --help
git status --short
```

추가 스모크:

```powershell
backend\.venv\Scripts\python.exe -m planforge parse tests\fixtures\plan.sample.md
backend\.venv\Scripts\python.exe -m planforge numcheck tests\fixtures\plan.sample.md --slides tests\fixtures\slides.sample.json
```

## Acceptance Criteria

위 최종 검증 커맨드 전체가 통과해야 한다. 특히:

- 전체 pytest 0 failures (기존 skip 제외).
- `frontend/openapi.json` diff 0.
- `npm run build` 성공.
- CLI 두 경로(`planforge`, `python -m planforge`)와 admin CLI 동작.
- `git status`에 `workspaces/`, `sources/`, `data/`, `backend/planforge/config.json`,
  `*.egg-info`, `step*-output.json`이 없어야 한다.

## 검증 절차

1. 최종 검증 커맨드를 실행한다.
2. 아키텍처 체크리스트:
   - 설계 원칙 계약 8개 위반이 없는가?
   - 모듈 경계·docloops 리프·planforge 웹 비의존이 유지되는가?
   - 빌더·마이그레이션·OpenAPI·SSE 계약이 불변인가?
3. 결과에 따라 `phases/refactor-standalone-cli/index.json`의 step 12를 갱신한다.

## 금지사항

- 문서를 갱신하면서 계약 문구(설계 원칙 8개·결정 번호)를 임의로 바꾸지 마라. 이유:
  CLAUDE.md는 하네스 가드레일이자 최상위 계약이다.
- 검증 실패를 문서 갱신으로 덮지 마라. 이유: AC 실패는 구현 결함이다.
- `frontend/openapi.json`·`types.gen.ts`를 재생성하지 마라. 이유: 이번 작업은 계약
  불변이며 diff 0이 AC다.
