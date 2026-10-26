# Step 4: plan-loading-authority

## 읽어야 할 파일

- `/CLAUDE.md` — 원칙 8(골격 검증), 원칙 1(SSOT)
- `/docs/ARCHITECTURE.md`, `/docs/ADR.md` (결정 17 — derive는 numcheck 게이트 아님)
- `/packages/planforge-cli/src/planforge/plan/model.py`, `parser.py`, `filter.py`, `__init__.py`
- `/packages/planforge-cli/src/planforge/derive.py`
- `/packages/planforge-cli/src/planforge/cli/commands/parse.py`, `derive.py` (step 2)
- `/backend/app/modules/derivatives/application/derive_build.py`
- `/backend/app/modules/plans/application/planrevise.py`
- `/backend/app/modules/interview/application/agent.py` — `_write_plan` (341-393)
- `/backend/app/modules/review/application/run_review.py` — 필터만 하고 골격 검증은 안 함
- `/tests/test_derive.py`, `test_plan_parser.py`, `test_plans_api.py`, `test_interview_api.py`

## 배경

"plan 파싱 → doc 선택 → 필터 → 골격 검증 → (미확정) 탐지"가 CLI·Deriver·인터뷰·
plan revise·review에 반복된다. 단일 로더로 모으고, 같은 plan을 두 번 파싱하는
경로를 제거한다. **검증 의미·에러 문자열·순서는 불변**이다.

## 작업

### 1. `plan/loader.py`

```python
@dataclass(frozen=True)
class PreparedPlan:
    plan: Plan
    doc: str | None
    slides: list[Slide]
    unconfirmed: list[int]

def prepare_plan(plan: Plan, doc: str | None = None, *,
                 strict_doc: bool = False) -> PreparedPlan: ...
def load_plan_for_doc(path: str | Path, doc: str | None = None, *,
                      strict_doc: bool = False) -> PreparedPlan: ...
def validate_each_doc(plan: Plan) -> None: ...
```

- `strict_doc=False`: CLI 동작 보존 — 미지정/알 수 없는 doc는 기존처럼 필터 결과가
  비고 골격 검증에서 실패한다.
- `strict_doc=True`: `Deriver._prepare`의 정확한 오류 문구
  `"문서 '{doc}'가 plan 메타 '산출 문서'({docs})에 없습니다"`를 유지한다.
- `validate_each_doc`은 문서별 `validate_skeleton(filter_slides(...))`만 담당한다.
  호출자별 래핑 문구는 호출자가 유지한다:
  - agent: `"ERROR: plan 골격 검증 실패 — 문서 '{doc}': {e}..."`
  - planrevise: `"plan 골격 검증 실패 — 문서 '{doc}': {e}"`

### 2. `Deriver`

- `_prepare`를 로더 위임으로 바꾼다 (`strict_doc=True`).
- `derive(..., prepared: PreparedPlan | None = None)`를 추가한다. `prepared`가 있으면
  재파싱하지 않는다.
- `DeriveResult`에 `doc: str | None = None`을 **필드 끝에** 추가한다. 기존 필드 순서
  유지.
- `derive_build.py`는 `parse_plan_file(plan_mirror).docs[0]` 대신 `res.doc`을 쓴다.
  `doc=None`이면 Deriver가 `plan.docs[0]`로 해석한 값이 들어간다.

### 3. 중복 검사 제거

- `plan/parser.py::_validate_plan`이 이미 `len(key_messages) != 3`을 강제한다.
- `agent._write_plan`의 `parse_plan_text` 직후 3-key 검사와
  `planrevise.validate_plan_markdown`의 3-key 검사는 도달 불가이므로 제거한다.
  **파서의 오류 문구와 호출자 래핑 문구는 그대로** 둔다.

### 4. CLI

`cli/commands/parse.py`의 `_filtered`와 `cli/commands/derive.py`의 사전 검사를
로더로 교체한다. `--allow-unconfirmed` 분기와 출력 문자열은 유지한다.

### 5. 테스트

`tests/test_plan_loader.py`:

- 기본 doc 선택, `strict_doc` true/false의 미지 doc 동작 차이.
- 골격 실패, `(미확정)` 슬라이드 번호 목록.
- `Deriver.derive(prepared=...)`가 파싱 경로와 동일한 `DeriveResult`를 내는지,
  `res.doc`이 채워지는지.

## Acceptance Criteria

```powershell
backend\.venv\Scripts\python.exe -m pytest tests\test_derive.py tests\test_plan_parser.py tests\test_plan_loader.py tests\test_plans_api.py tests\test_interview_api.py -q
```

## 검증 절차

1. AC를 실행한다.
2. 체크리스트:
   - 골격 검증 시점·의미가 바뀌지 않았는가?
   - `run_review`가 골격 검증을 하지 않는 기존 계약을 유지했는가?
   - 오류 문구·메시지 순서가 동일한가?
3. `phases/refactor-standalone-cli/index.json`의 step 4를 갱신한다.

## 금지사항

- `run_review`에 골격 검증을 추가하지 마라. 이유: review는 필터만 하고, derive의
  골격 게이트(원칙 8)와 역할이 다르다.
- `DeriveResult` 기존 필드 순서를 바꾸지 마라. 이유: 위치 인자·직렬화 계약.
- 검증 에러 문구를 통일하지 마라. 이유: 인터뷰·revise 테스트가 문자열을 고정한다.
