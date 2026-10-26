# Step 6: job-handlers-refactor

## 읽어야 할 파일

- `/CLAUDE.md` — 원칙 1(SSOT), 원칙 5(무손실 채번), 원칙 8(골격)
- `/docs/ADR.md` — 결정 15(진행 기록 불변식), 16(오류 라벨), 17(수치 판정 이관)
- `/backend/app/modules/derivatives/application/derive_build.py`
- `/backend/app/modules/review/application/run_review.py`
- `/backend/app/modules/plans/application/plan_revise_job.py`
- Step 5 산출물: `jobs/presentation/responses.py`, `jobs/facade.py`,
  `docloops/facade.py`, `app/shared/collections.py`, `app/shared/factline.py`
- Step 4 산출물: `DeriveResult.doc`, `plan/loader.py`
- `/tests/test_derive.py`, `test_review.py`, `test_jobs_worker.py`,
  `test_plan_revise_from_review.py`, `test_enqueue_visibility.py`

## 배경

세 job 핸들러가 각각 100줄 안팎이며 로드·LLM·빌드·영속·결과 조립이 한 함수에 섞여
있다. 단일 책임 함수로 나누고 step 5 헬퍼를 적용한다. **job 결과·진행 기록·예외
분류·자동 검수 동작은 불변**이다.

## 작업

### 1. `derive_build.py`

`run_derive_build`를 다음 private 함수로 분해한다(이름은 재량, 역할은 고정):

- `_load_job_context(session, job)` — plan/project 조회 + APPROVED 게이트.
- `_resolve_workspace(plan, project, session)` — `docloops.resolve_workspace_root(...)`,
  root가 다를 때만 `ensure_doc_ws`.
- `_run_llm_phase(...)` — `Deriver`, `report_progress_safe` 기반 `progress`/`on_attempt`,
  LLM 변환. 반환값에 `res.doc`을 포함한다.
- `_run_build_phase(...)` — `atomic_build` + ppt/doc 빌더 어댑터.
- `_persist_rows(...)` — Derivative/Build 행 생성. **모든 `session.add`는
  `atomic_build` 이후**라는 불변식 유지.
- `_maybe_enqueue_review(...)` — 결정 17 red 잔여 시 자동 검수 큐잉. 모든
  `report_progress` 뒤에 호출.
- `_job_result(...)` — `job.result` dict 조립. 키·값·순서 불변.

추가 적용:

- `parse_plan_file(plan_mirror).docs[0]` → `res.doc`.
- `_read_json` → `planforge.common.io.read_json` (동일 포맷).
- `Build.file_path`의 `output/{f.name}` 형식 유지.
- `format_build_filename`은 표시용 문자열에만 사용(파일명 생성 로직은 빌더 소유).

### 2. `run_review.py`

다음으로 분해한다:

- `_load_context(...)` — project/plan/APPROVED, doc ws + mirror.
- `_check_derivative_docs(...)` — 같은 plan 세대 파생물 최신-per-key 선택
  (`latest_by_key`), numcheck 대조.
- `_check_generation(...)` — 세대 대응성. 문서 plan은 doc_slug로 좁힌다.
- `_check_tags_and_facts(...)` — `check_doc_tags`, `check_facts`.
- `_run_llm_review(...)` — 진행 기록(`report_progress_safe`) + LLM 검수,
  실패해도 결정론 findings 보존.
- `_build_report(...)` — counts + `ReviewReport` add/flush + result dict.

Finding dict는 `asdict(f)`와 기존 수동 `add(...)`를 함께 쓰되 키 순서
`code, severity, where, message, suggestion`를 유지한다.

### 3. `plan_revise_job.py`

다음으로 분해한다:

- `_load_context(...)` — plan/project/review 조회·세대 일치 검사.
- `_select_findings(...)` — 현재의 **조용한 범위 필터** 유지(API의 409 정책과 다름).
- `_run_llm(...)` — `report_progress_safe`, `LLMRegistry`, `plan_revise`→`review`
  폴백, `run_plan_revise`.
- `_persist_new_generation(...)` — `validate_plan_markdown` 이중 방어, 무변경 검사,
  `create_generation`, 미러 기록.

`validate_plan_markdown` 이중 호출은 의도적 방어이므로 제거하지 않는다.

### 4. 테스트

기존 테스트를 그대로 통과시킨다. 필요하면 다음을 추가한다:

- `derive_build`의 `res.doc` 사용 경로(문서 plan).
- `report_progress_safe` 적용 후에도 progress step/detail 문자열이 동일한지.
- `run_review`의 finding dict 키 순서.

## Acceptance Criteria

```powershell
backend\.venv\Scripts\python.exe -m pytest tests\test_derive.py tests\test_review.py tests\test_jobs_worker.py tests\test_plan_revise_from_review.py tests\test_enqueue_visibility.py -q
```

## 검증 절차

1. AC를 실행한다.
2. 체크리스트:
   - `job.result` 키·값·순서와 progress step/detail이 동일한가?
   - 예외 클래스와 `JobErrorClass` 분류가 동일한가?
   - 자동 검수 큐잉 시점(모든 report_progress 뒤)이 유지되는가?
   - SSOT 미러 경로·`atomic_build` 어댑터가 동일한가?
3. `phases/refactor-standalone-cli/index.json`의 step 6을 갱신한다.

## 금지사항

- `session.add`를 `atomic_build` 이전으로 옮기지 마라. 이유: 빌드 실패 시 고아
  Derivative가 남는다(결정 15).
- `report_progress`를 대기 중 도메인 행이 있는 시점에 호출하지 마라. 이유: 세션 전체
  커밋으로 고아 행이 커밋된다.
- 진행 기록 step 이름(`llm`, `build`)·detail 문구·로그 태그를 바꾸지 마라.
- `plan_revise_job`의 조용한 범위 필터를 API 정책(409)으로 바꾸지 마라. 이유:
  의도적으로 다른 정책이며 이번 범위는 동작 불변이다.
