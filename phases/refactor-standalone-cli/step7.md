# Step 7: plans-review-apis

## 읽어야 할 파일

- `/CLAUDE.md`, `/docs/ARCHITECTURE.md`, `/docs/ADR.md` (202 계약, 모듈 경계)
- `/backend/app/modules/derivatives/presentation/api.py`
- `/backend/app/modules/review/presentation/api.py`
- `/backend/app/modules/plans/presentation/api.py`
- `/backend/app/modules/plans/application/service.py`
- `/backend/app/modules/projects/presentation/api.py`
- `/backend/app/modules/docloops/presentation/api.py`, `presentation/schemas.py`
- Step 5 산출물: `jobs/presentation/responses.py`, `docloops/facade.py`,
  `DocLoopOut.from_row`
- `/tests/test_plans_api.py`, `test_projects_api.py`, `test_docloops_api.py`,
  `test_enqueue_visibility.py`, `test_facts_api.py`
- `/frontend/openapi.json` — 계약 (수정 금지)

## 배경

세 POST 엔드포인트가 `enqueue → commit → JobOut`을 복제하고, projects/docloops API가
`DocLoopOut`을 각자 조립하며, `plans.service._mirror_root`가 doc ws 해석을 복제한다.
이 step은 API 계층 중복을 제거한다. **라우트·스키마·상태 코드·에러 문구 불변**.

## 작업

### 1. enqueue 엔드포인트 통일

다음을 `enqueue_accepted(db, project_id, job_type, payload)`로 교체한다:

- `derivatives/presentation/api.py::enqueue_derivative`
- `review/presentation/api.py::enqueue_review`
- `plans/presentation/api.py::revise_plan_from_review`

- 응답 모델 `JobOut`, `status_code=202`, `db.commit()` 시점(반환 전)을 유지한다.
- 각 엔드포인트의 사전 검증 409/404와 문구는 그대로 둔다.

### 2. doc ws 해석 통일

- `plans/application/service.py::_mirror_root`가 `docloops.resolve_workspace_root(...)`
  에 위임하도록 바꾼다. 기존 `ensure` 동작(미러 디렉토리 생성)을 유지한다.
- `review/run_review.py`·`derive_build.py`는 step 6에서 이미 위임했다면 그대로 둔다.
- `interview/agent.py::_mirror_root`도 위임할 수 있으나, 세션 객체(`self.sess`)에서
  project_id/path를 꺼내는 기존 계약을 유지한다.

### 3. DocLoopOut 조립 통일

- `projects/presentation/api.py::_docloop_out`를 `DocLoopOut.from_row(row, gen)`로
  교체한다.
- `docloops/presentation/api.py`의 동일 조립도 `from_row`로 교체한다.
- `_docloops_batch`의 정렬 순서(`DOC_KINDS` 순, 미상 slug는 뒤)는 그대로 둔다.
- `DOC_KINDS` 순서를 facade export로 단일화할 수 있으면 하되, 순환·경계 위험이 있으면
  유지하고 summary에 남긴다.

### 4. 유예

- `plans/api.py`와 `plan_revise_job.py`의 review 선택 정책 통합(D24)은 하지 않는다 —
  API는 범위 밖 409, job은 조용히 필터.
- `facts/presentation/api.py`의 `_validated_source_path` 보안 동작(D22)은 건드리지 않는다.

## Acceptance Criteria

```powershell
backend\.venv\Scripts\python.exe -m pytest tests\test_plans_api.py tests\test_projects_api.py tests\test_docloops_api.py tests\test_enqueue_visibility.py tests\test_facts_api.py -q
backend\.venv\Scripts\python.exe backend\scripts\export_openapi.py
git diff --exit-code -- frontend/openapi.json
```

## 검증 절차

1. AC를 실행한다.
2. 체크리스트:
   - OpenAPI diff가 0인가?
   - 202 응답 전 커밋 가시성이 유지되는가?
   - 에러 문구·상태 코드가 동일한가?
   - docloops 리프 의존 방향이 유지되는가?
3. `phases/refactor-standalone-cli/index.json`의 step 7을 갱신한다.

## 금지사항

- `frontend/openapi.json`·`types.gen.ts`를 수정하지 마라. 이유: 이번 작업은 계약
  불변이며 diff 0이 AC다.
- enqueue 커밋을 facade나 teardown으로 옮기지 마라. 이유: 202 직후 /jobs 조회가
  잡을 놓친다.
- review 선택 정책을 통합하지 마라. 이유: API/job 정책이 의도적으로 다르다(유예).
