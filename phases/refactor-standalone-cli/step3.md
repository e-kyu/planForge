# Step 3: admin-cli

## 읽어야 할 파일

- `/CLAUDE.md`, `/docs/ARCHITECTURE.md`
- `/backend/scripts/_bootstrap.py` (step 0 최소 버전)
- `/backend/scripts/export_openapi.py`, `/backend/scripts/job_timing_report.py`
- `/backend/app/shared/config.py`, `/backend/app/shared/db.py`, `/backend/app/main.py`
- `/frontend/openapi.json` — 계약 산출물 (수정 금지)
- `/tests/test_alembic_upgrade.py` — subprocess 부트스트랩 관례

## 배경

두 관리 스크립트가 각자 `sys.path`와 DB URL을 해석한다. 앱 인지 관리 CLI를
`backend/scripts/admin.py`로 모으고, 기존 경로는 얇은 shim으로 유지한다.
**`planforge/`에는 앱 인지 코드를 넣지 않는다.**

## 작업

### 1. `_bootstrap.py` 확장

```python
BACKEND_DIR: Path
REPO_ROOT: Path
PACKAGE_SRC: Path
def ensure_paths() -> None: ...   # PACKAGE_SRC를 sys.path 최우선으로
def database_url() -> str: ...    # Settings().database_url
```

- `database_url()`은 `app.shared.config`를 lazy import한다.
- 기존 `job_timing_report.py`의 수동 URL fallback을 이 함수로 교체한다.

### 2. `admin.py`

```python
def cmd_openapi(args: argparse.Namespace) -> int: ...
def cmd_job_timing(args: argparse.Namespace) -> int: ...
def build_parser() -> argparse.ArgumentParser: ...
def main(argv: list[str] | None = None) -> int: ...
```

- 서브커맨드: `openapi`, `job-timing`.
- `openapi`: 현재 `export_openapi.py`와 동일하게 `create_app(start_worker=False)`의
  schema를 `frontend/openapi.json`에 `ensure_ascii=False, indent=2`로 쓴다.
  출력 경로·바이트·`written: ...` 메시지를 유지한다.
- `job-timing`: 현재 `job_timing_report.py`의 컬럼·한국어 라벨·요약 출력을 그대로
  옮긴다. DB URL은 `_bootstrap.database_url()`을 쓴다. 읽기 전용 동작 유지.

### 3. 기존 스크립트는 shim

`export_openapi.py`와 `job_timing_report.py`는 `main()`에서
`admin.main(["openapi"])`, `admin.main(["job-timing"])`를 호출하고 반환값을
`sys.exit`로 전달한다. 기존 문서화된 실행 경로가 그대로 동작해야 한다.

### 4. 테스트

`tests/test_scripts_admin.py`:

- `_bootstrap.ensure_paths()` 후 `app`·`planforge` import가 가능한지.
- `_bootstrap.database_url()`이 `DATABASE_URL` 환경변수를 존중하는지.
- `admin.main(["--help"])`가 0으로 끝나는지.
- 기존 shim 스크립트가 `main`을 노출하는지.
- `openapi`는 monkeypatch로 `create_app`/출력 경로를 대체해 호출 여부만 검증한다
  (실제 계약 파일을 덮어쓰지 않는다).

## Acceptance Criteria

```powershell
backend\.venv\Scripts\python.exe backend\scripts\export_openapi.py
git diff --exit-code -- frontend/openapi.json
backend\.venv\Scripts\python.exe backend\scripts\job_timing_report.py
backend\.venv\Scripts\python.exe backend\scripts\admin.py --help
backend\.venv\Scripts\python.exe -m pytest tests\test_scripts_admin.py -q
```

## 검증 절차

1. AC를 실행한다.
2. 체크리스트:
   - `admin.py`가 `planforge/`가 아니라 `backend/scripts/`에 있는가?
   - OpenAPI 출력이 바이트 동일한가?
   - `job_timing_report.py` 출력 문구가 동일한가?
3. `phases/refactor-standalone-cli/index.json`의 step 3을 갱신한다.

## 금지사항

- `frontend/openapi.json`·`types.gen.ts`를 변경하지 마라. 이유: 이 step은 CLI
  구조 변경이며 계약 변경이 아니다.
- `job_timing_report.py`의 출력 문구·컬럼을 바꾸지 마라. 이유: 사용자 진단 도구 계약.
- `planforge/`에 `app`/DB 의존 코드를 넣지 마라. 이유: 웹 비의존 계약 위반이다.
