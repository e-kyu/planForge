# Step 1: cli-common-kernel

## 읽어야 할 파일

- `/CLAUDE.md`, `/docs/ARCHITECTURE.md`, `/docs/ADR.md`
- `/packages/planforge-cli/src/planforge/__init__.py`, `derive.py`, `numcheck.py`, `review.py`
- `/packages/planforge-cli/src/planforge/plan/model.py`, `parser.py`, `filter.py`
- `/packages/planforge-cli/src/planforge/llm/provider.py`, `llm/loops.py`
- `/packages/planforge-cli/src/planforge/common/configpath.py` (step 0 산출물)
- `/backend/app/shared/workspace.py` — 재수출 대상
- `/tests/test_plan_parser.py`, `test_filter_skeleton.py`, `test_numcheck.py`,
  `test_workspace_doc_root.py`, `test_atomic_build.py`

## 배경

Step 0에서 엔진을 독립 패키지로 옮겼다. 이 step은 반복되는 UTF-8/JSON I/O, 상수,
slug 정규식, 빌드 파일명 포맷/파싱을 `planforge/common/`으로 모은다. **동작·문자열·
판정 의미는 불변**이다.

## 작업

### 1. `common/io.py`

```python
def read_text_utf8(path: str | Path) -> str        # encoding="utf-8-sig"
def read_json(path: str | Path) -> Any            # utf-8-sig
def write_json(path: str | Path, obj: Any) -> Path # ensure_ascii=False, indent=2, utf-8
```

- 기존 `json.dumps(..., ensure_ascii=False, indent=2)`와 **바이트 동일**해야 한다
  (trailing newline 추가 금지).
- `derive.py`의 work JSON 쓰기, `derive_build.py`의 읽기 등 동일 호출을 이 함수로
  교체할 수 있는 곳부터 적용한다. 적용이 위험한 곳은 남겨도 된다.

### 2. `common/const.py`

```python
UNCONFIRMED_PREFIX = "(미확정"
UNCONFIRMED_EXACT = "(미확정)"
DEFAULT_DOC_NAME = "제안서"
DERIVATIVE_KINDS = ("slides", "report")
REPORT_FORMATS = ("md", "html", "docx")
KEY_MESSAGE_COUNT = 3
MAX_ARCH_GROUPS = 6
MAX_ARCH_ITEMS = 6
```

- `numcheck.py`의 `UNCONFIRMED = "(미확정"`은 `UNCONFIRMED_PREFIX` 별칭으로 유지한다.
- `plan/parser.py`의 기본 문서 `"제안서"`, arch 6 한도, 핵심 메시지 3개를 상수로
  치환한다. **에러 문구의 숫자 표기는 그대로** 둔다.
- `derive.py`의 `("slides", "report")`, `("md","html","docx")`, `(미확정` 상수를
  상수 참조로 바꾼다.
- `(미확정` (prefix)과 `(미확정)` (exact)의 **매칭 의미를 통합하지 않는다** —
  compact는 exact, numcheck/derive/review는 prefix다.

### 3. `common/slug.py`

```python
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MAX_SLUG_LENGTH = 64
def is_valid_slug(slug: str) -> bool: ...
```

`backend/app/shared/workspace.py`는 `SLUG_RE`를 여기서 import해 재수출하고,
`validate_slug`·`WorkspaceError`·에러 메시지는 그대로 둔다.
`projects/presentation/schemas.py`의 중복 정규식 검사는 `is_valid_slug`를 쓰도록
바꿔도 되지만, 422 동작과 메시지는 유지한다.

### 4. `common/buildfs.py`

```python
BUILD_VER_RE = re.compile(r"_v(\d+)\.[A-Za-z]+$")
def parse_build_filename(name: str) -> tuple[str, int, str] | None: ...
def format_build_filename(title: str, version_no: int, ext: str) -> str: ...
```

`app/shared/workspace.py`는 `BUILD_VER_RE`·`parse_build_filename`을 재수출한다.
`format_build_filename`은 `f"{title}_v{version_no:02d}.{ext}"`와 동일해야 한다.

### 5. `plan/model.py`

`SLIDE_TYPES_KO_TO_EN`의 역방향 `SLIDE_TYPES_EN_TO_KO`를 한 번만 만든다.
`derive.py`의 `_type_ko` dict를 이 역방향 맵으로 교체한다. `_fmt_plan_value`가
단순 `str` 래퍼라면 제거하고 호출부를 `str(...)`로 바꾼다(동작 동일).

### 6. 신규 테스트

`tests/test_common_utils.py`:

- BOM 있는 UTF-8 읽기, JSON round-trip, `write_json`의 정확한 바이트 형식.
- slug 경계(64자, 선행 하이픈, 대문자, 빈 문자열).
- `format_build_filename`/`parse_build_filename` 왕복, `v01` zero-pad, 확장자 소문자.

## Acceptance Criteria

```powershell
backend\.venv\Scripts\python.exe -m pytest tests\test_plan_parser.py tests\test_filter_skeleton.py tests\test_numcheck.py tests\test_workspace_doc_root.py tests\test_atomic_build.py tests\test_common_utils.py -q
```

## 검증 절차

1. AC를 실행한다.
2. 체크리스트:
   - `planforge/common/*`가 표준 라이브러리만 import하는가?
   - `app.shared.workspace`의 공개 심볼이 유지되는가?
   - `(미확정`/`(미확정)` 의미가 바뀌지 않았는가?
3. `phases/refactor-standalone-cli/index.json`의 step 1을 갱신한다
   (completed+summary / error+error_message / blocked+blocked_reason).

## 금지사항

- `(미확정`과 `(미확정)`의 매칭 의미를 통합하지 마라. 이유: 판정 동작이 바뀐다.
- slug 검증을 `planforge/`로 옮겨 `WorkspaceError`를 import하게 하지 마라. 이유:
  엔진의 웹 비의존 계약 위반이다.
- 기존 에러 문구·숫자 표기를 상수화하면서 바꾸지 마라. 이유: 테스트가 문자열을 고정한다.
