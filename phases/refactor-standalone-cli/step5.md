# Step 5: app-shared-helpers

## 읽어야 할 파일

- `/CLAUDE.md`, `/docs/ARCHITECTURE.md`, `/docs/ADR.md` (결정 15·17·22)
- `/backend/app/modules/jobs/facade.py`, `presentation/schemas.py`, `infrastructure/models.py`
- `/backend/app/modules/docloops/facade.py`, `presentation/schemas.py`, `application/service.py`
- `/backend/app/modules/projects/presentation/api.py` — `_docloop_out`
- `/backend/app/shared/workspace.py` — `doc_ws_root`, `ensure_doc_ws`
- `/backend/app/modules/facts/application/compact.py` — `fact_line`
- `/backend/app/modules/interview/application/agent.py` — 팩트 라인 2곳
- `/backend/app/modules/review/application/review_agent.py` — 팩트 라인
- `/tests/test_enqueue_visibility.py`, `test_workspace_doc_root.py`,
  `test_docloops_service.py`, `test_jobs_worker.py`

## 배경

여러 모듈이 같은 작은 패턴을 복제한다. 이 step은 **헬퍼만 추가**하고, 호출부의
대량 수정은 다음 step으로 미룬다. 모든 헬퍼는 기존 동작·문구를 정확히 보존한다.

## 작업

### 1. `jobs/presentation/responses.py`

```python
def enqueue_accepted(db: Session, project_id: int, job_type: JobType,
                     payload: dict) -> JobOut: ...
```

- 내부: `job = enqueue(db, project_id, job_type, payload)` → `db.commit()` →
  `JobOut.model_validate(job)`.
- **커밋은 반드시 반환 전**. `tests/test_enqueue_visibility.py`의 202 계약을 유지한다.
- facade의 `enqueue` 시그니처를 바꾸지 않는다.

### 2. `jobs/facade.py::report_progress_safe`

```python
def report_progress_safe(db: Session, job, step: str, *,
                         log_tag: str, **kw) -> None: ...
```

- 내부에서 `report_progress(...)`를 try/except로 감싸고, 실패 시
  `print(f"[{log_tag}] job #{job.id} 진행 기록 실패", flush=True)`를 출력한다.
- 기존 세 호출부의 로그 태그(`derive`, `review`, `plan_revise`)와 문구를 그대로
  재현할 수 있어야 한다.
- `report_progress` 자체의 커밋 계약은 불변.

### 3. `docloops/facade.py::resolve_workspace_root`

```python
def resolve_workspace_root(db: Session, project_id: int, workspace_path,
                           doc_slug: str | None, *, ensure: bool = False) -> Path: ...
```

- `has_doc_layout(db, project_id)` + `app.shared.workspace.doc_ws_root` +
  선택적 `ensure_doc_ws`.
- docloops 리프 규칙 유지 — `app.shared`만 import하고 타 모듈 facade는 import하지 않는다.
- `ensure=False`일 때 `derive_build`의 "doc root가 다를 때만 ensure" 동작을 호출자가
  그대로 구현할 수 있어야 한다.

### 4. `docloops/presentation/schemas.py::DocLoopOut.from_row`

```python
@classmethod
def from_row(cls, row, gen: object | None) -> "DocLoopOut": ...
```

- `doc_slug`, `label=doc_label(row.doc_slug)`, `status=str(row.status)`,
  `plan_version=gen.version_no if gen else None`, `plan_id=gen.id if gen else None`.
- 기존 `projects/api.py::_docloop_out`와 정확히 같은 값을 낸다.
- Pydantic 필드·순서·직렬화는 불변.

### 5. `app/shared/collections.py`

```python
def latest_by_key(rows, key) -> dict: ...
```

- 입력 순서를 유지하며 `key(row)`별 첫 행만 채택한다(정렬은 호출자가 보장).
- `plans/facade.py`의 두 최신-per-key 루프와 `run_review.py`의 derivative 최신 선택에
  재사용 가능해야 한다.

### 6. `app/shared/factline.py`

```python
def format_fact_line(date, content: str, source: str, *,
                     marker: str = "", bullet: bool = False) -> str: ...
```

- 기본: `"[{date_text}] {content} (출처: {source})"`.
- `date`가 `date`/`datetime`이면 `isoformat()`, 문자열이면 그대로.
- `marker`가 있으면 `" {marker}"`를 뒤에 붙인다(compact의 `fact_line` 동작).
- `bullet=True`면 `"- "` 접두사를 붙인다(agent `_turn_context`, review_agent).
- 이 헬퍼는 **추가만** 하고 기존 `fact_line`은 아직 그대로 둔다. step 9에서 위임.

### 7. 테스트

`tests/test_jobs_helpers.py` 신규:

- `enqueue_accepted`가 반환 전에 커밋해 다른 세션에서 보이는지.
- `report_progress_safe`가 DB 오류를 삼키고 정확한 로그 태그를 출력하는지(capsys).
- `latest_by_key`의 첫-행 채택.
- `format_fact_line`의 4가지 변형(기본/마커/불릿/문자열 날짜).

`tests/test_workspace_doc_root.py` 확장:

- `resolve_workspace_root`의 레거시/문서 레이아웃/`ensure` 동작.

## Acceptance Criteria

```powershell
backend\.venv\Scripts\python.exe -m pytest tests\test_jobs_helpers.py tests\test_workspace_doc_root.py tests\test_docloops_service.py tests\test_enqueue_visibility.py -q
```

## 검증 절차

1. AC를 실행한다.
2. 체크리스트:
   - `app/shared`가 모듈 facade를 import하지 않는가?
   - docloops가 리프 모듈로 남았는가?
   - 202 커밋 가시성 계약이 유지되는가?
3. `phases/refactor-standalone-cli/index.json`의 step 5를 갱신한다.

## 금지사항

- `LLMRegistry` 팩토리/폴백 헬퍼를 새로 만들지 마라. 이유: 기존 LLM 주입 지점 위
  추상화 금지(ADR 편차 2).
- `docloops`가 타 모듈 facade를 import하게 하지 마라. 이유: 리프 모듈 계약 위반.
- 기존 facade 공개 시그니처를 바꾸지 마라. 이유: 테스트·타 모듈이 직접 import한다.
