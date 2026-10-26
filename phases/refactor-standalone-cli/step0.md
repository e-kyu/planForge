# Step 0: engine-package-move

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md` — 설계 원칙 계약 8개 (최상위)
- `/docs/ARCHITECTURE.md`, `/docs/ADR.md` — 모듈 경계·빌더 불변 계약
- `/backend/planforge/__init__.py`, `__main__.py`, `derive.py`, `numcheck.py`, `review.py`
- `/backend/planforge/plan/`, `llm/`, `builders/` — 이동 대상 전체 구조
- `/backend/app/shared/config.py` — LLM 설정 기본 경로
- `/backend/app/shared/workspace.py` — slug·빌드 파일명 유틸
- `/backend/scripts/export_openapi.py`, `/backend/scripts/job_timing_report.py`
- `/conftest.py`, `/pytest.ini`, `/backend/requirements.txt`
- `/backend/Dockerfile`, `/docker-compose.yml`, `/.gitignore`
- `/tests/test_design_tokens.py`, `/tests/test_derive.py`, `/tests/test_contract_builders.py`
- `/docs/UI_GUIDE.md`, `/backend/CLAUDE.md`, `/backend/README.md`, `/README.md`

## 배경

엔진(`backend/planforge/`)을 웹 백엔드와 분리된 **설치 가능한 독립 CLI 패키지**로
옮긴다. 목표는 `packages/planforge-cli/` + `pyproject.toml` + `planforge` 콘솔
스크립트이며, backend는 이 패키지에 의존한다. **동작·문자열·계약은 불변**이다.
빌더 3종은 파일만 이동하고 내용은 바이트 동일하게 유지한다.

## 작업

### 1. 패키지 스캐폴드

`packages/planforge-cli/pyproject.toml`을 만든다 (내용은 아래를 그대로 사용):

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "planforge-cli"
version = "0.1.0"
description = "PlanForge deterministic document pipeline and CLI"
requires-python = ">=3.12"
dependencies = [
  "python-pptx>=1.0",
  "python-docx>=1.1",
  "langchain-core==1.6.5",
  "langchain-openai==1.6.6",
  "langgraph==1.2.12",
]

[project.scripts]
planforge = "planforge.__main__:main"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
planforge = ["llm/prompts/*.md"]
```

`packages/planforge-cli/README.md`에 설치(`pip install -e packages/planforge-cli`),
`planforge ...`와 `python -m planforge ...` 호환, 실행 위치(`backend/`)를 적는다.

### 2. 파일 이동 (`git mv`)

먼저 `packages/planforge-cli/src/planforge/`를 만든 뒤, **Python 파일·디렉토리만**
이동한다. PowerShell 예:

```powershell
New-Item -ItemType Directory -Force packages\planforge-cli\src\planforge | Out-Null
git mv backend\planforge\__init__.py packages\planforge-cli\src\planforge\__init__.py
git mv backend\planforge\__main__.py packages\planforge-cli\src\planforge\__main__.py
git mv backend\planforge\derive.py packages\planforge-cli\src\planforge\derive.py
git mv backend\planforge\numcheck.py packages\planforge-cli\src\planforge\numcheck.py
git mv backend\planforge\review.py packages\planforge-cli\src\planforge\review.py
git mv backend\planforge\builders packages\planforge-cli\src\planforge\builders
git mv backend\planforge\llm packages\planforge-cli\src\planforge\llm
git mv backend\planforge\plan packages\planforge-cli\src\planforge\plan
```

- `backend/planforge/config.example.json`과 `backend/planforge/config.json`은
  **이동하지 않는다** — 런타임 설정 경로(`backend/planforge/config.json`)와
  `.claude/settings.json`의 deny 경로를 보존한다.
- `backend/planforge/__pycache__` 등 ignored 산출물은 그대로 둔다.
- 빌더 파일 내용은 한 바이트도 바꾸지 않는다.

### 3. 설정 경로 호환

`packages/planforge-cli/src/planforge/common/__init__.py`와
`common/configpath.py`를 만든다. 시그니처:

```python
def resolve_config_path(explicit: str | None = None) -> Path: ...
```

우선순위(기존 동작 보존):
1. `explicit` (`--config`)
2. `PLANFORGE_CONFIG` 환경변수
3. `Path.cwd() / "planforge" / "config.json"` — 문서화된 실행 위치가 `backend/`이므로
   기존 기본 경로와 동일하다.
4. 패키지 디렉토리 인접 `config.json` (설치 환경 폴백)

`planforge/__main__.py`(이동된 파일)의 `cmd_derive`가 이 함수를 쓰도록 바꾼다.
에러 문구와 `return 2` 동작은 그대로 유지한다.

### 4. 테스트 import 경로

루트 `conftest.py`에서 `packages/planforge-cli/src`를 **가장 먼저**,
`backend`를 그 다음에 `sys.path`에 넣는다. `backend/planforge`에는 `__init__.py`가
없는 설정 디렉토리만 남으므로 정규 패키지가 항상 우선해야 한다.

### 5. 스크립트 부트스트랩

`backend/scripts/_bootstrap.py` 최소 버전을 만든다:

```python
BACKEND_DIR, REPO_ROOT, PACKAGE_SRC
def ensure_paths() -> None: ...   # PACKAGE_SRC를 sys.path 최우선으로
def database_url() -> str: ...    # app.shared.config.Settings().database_url
```

`export_openapi.py`와 `job_timing_report.py`가 수동 `sys.path.insert` 대신
`ensure_paths()`를 쓰도록 바꾼다. 출력과 동작은 불변.

### 6. Docker/배포

- `docker-compose.yml`의 backend build를 `context: .`, `dockerfile: backend/Dockerfile`로.
- `backend/Dockerfile`: `requirements.txt` 설치 → `packages/planforge-cli` 복사·설치
  (`pip install --no-cache-dir --no-build-isolation packages/planforge-cli`) →
  `backend` 복사. `WORKDIR /srv/backend` 유지.
- 루트 `.dockerignore` 추가: `backend/.venv`, `**/__pycache__`, `.git`, `workspaces`,
  `data`, `sources`, `node_modules`, `frontend`, `.e2e-shots`, `phases`.
- `.gitignore`에 `*.egg-info/`, `packages/planforge-cli/build/`, `dist/` 추가.

### 7. 테스트 경로 갱신

`tests/test_design_tokens.py`의 `BUILDERS` 경로를
`packages/planforge-cli/src/planforge/builders/...`로 바꾼다. 검증 로직·theme 값은
그대로 둔다.

### 8. 문서 경로 참조만 갱신

`CLAUDE.md`, `backend/CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/UI_GUIDE.md`에서
엔진 파일 경로를 새 위치로 바꾼다. 단, `backend/planforge/config.json`과
`config.example.json`은 기존 경로를 유지한다. 구조 설명·ADR 결정 기록은 step 12에서
완성한다.

## Acceptance Criteria

```powershell
backend\.venv\Scripts\python.exe -m pip install --no-build-isolation -e packages\planforge-cli
backend\.venv\Scripts\python.exe -m pytest
backend\.venv\Scripts\python.exe -m planforge --help
backend\.venv\Scripts\python.exe backend\scripts\export_openapi.py
git diff --exit-code -- frontend/openapi.json
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트:
   - `planforge/`가 FastAPI/SQLAlchemy/`app.*`를 import하지 않는가?
   - 빌더 3종이 바이트 동일한가? (`git diff --stat`으로 내용 변경 0 확인)
   - 모듈 경계·동작 불변 계약을 지켰는가?
3. 결과에 따라 `phases/refactor-standalone-cli/index.json`의 step 0을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 3회 시도 후 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 빌더 `build_ppt.py`·`build_doc.py`·`theme.py`의 내용을 수정하지 마라. 이유: legacy
  바이트 동일 이식본 계약이며 계약 테스트가 출력 바이트를 고정한다.
- `backend/planforge/config.json`·`config.example.json`을 이동·삭제하지 마라. 이유:
  런타임 설정 경로와 `.claude/settings.json` deny 경로를 보존해야 한다.
- `frontend/openapi.json`·`types.gen.ts`·마이그레이션을 변경하지 마라. 이유: 이 step은
  구조 이동이며 API 계약 변경이 아니다.
- `workspaces/`·`sources/`·`data/`를 수정하지 마라. 이유: SSOT 가드훅이 차단한다.
