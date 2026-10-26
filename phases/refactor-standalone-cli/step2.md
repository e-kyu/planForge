# Step 2: cli-entrypoint-split

## 읽어야 할 파일

- `/packages/planforge-cli/src/planforge/__main__.py` — 현재 CLI 전체
- `/packages/planforge-cli/src/planforge/common/configpath.py` (step 0)
- `/packages/planforge-cli/src/planforge/common/const.py`, `common/io.py` (step 1)
- `/packages/planforge-cli/src/planforge/derive.py`, `numcheck.py`, `plan/`
- `/packages/planforge-cli/pyproject.toml`
- `/tests/test_derive.py` — `from planforge import __main__ as m` 계약
- `/backend/README.md` — CLI 명령·출력 문서

## 배경

`__main__.py` 하나에 argparse 등록과 5개 명령 본문이 섞여 있다. 이를
`planforge/cli/` 패키지로 쪼개고, `__main__.py`는 **호환 shim**으로 남긴다. 명령 이름·
플래그·출력 문자열·exit code는 전부 유지한다.

## 작업

### 1. `cli/commands/` 분리

다음 파일을 만든다.

- `cli/commands/parse.py::cmd_parse(args) -> int`
- `cli/commands/numcheck.py::cmd_numcheck(args) -> int`
- `cli/commands/derive.py::cmd_derive(args) -> int`
- `cli/commands/build.py::cmd_build_ppt(args) -> int`, `cmd_build_doc(args) -> int`

기존 본문을 **그대로 복사**하고 import만 조정한다. `derive`의
`resolve_config_path`, `read_json` 등 step 0/1 산출물을 사용한다.
무거운 import(`langgraph`, `langchain-openai`, 빌더)는 기존처럼 명령 함수 안에서만
수행한다 — `parse`/`numcheck`가 무거운 의존성을 끌어오면 안 된다.

### 2. `cli/main.py`

```python
def build_parser() -> argparse.ArgumentParser: ...
def main(argv: list[str] | None = None) -> int: ...
```

- `prog="planforge"`, description, 서브커맨드 이름·help·choices·기본값을 그대로 옮긴다.
- `args.fn(args)` 호출과 `if __name__ == "__main__": sys.exit(main())` 패턴을 유지한다.

### 3. `__main__.py` shim

```python
import argparse  # legacy 재수출
from .cli.commands.build import cmd_build_doc, cmd_build_ppt
from .cli.commands.derive import cmd_derive
from .cli.commands.numcheck import cmd_numcheck
from .cli.commands.parse import cmd_parse
from .cli.main import build_parser, main

if __name__ == "__main__":
    raise SystemExit(main())
```

- `tests/test_derive.py`가 `m.argparse.NameSpace`와 `m.cmd_derive(ns)`를 쓰므로
  `argparse`와 모든 `cmd_*`가 module attribute로 보여야 한다.
- `python -m planforge ...`가 계속 동작해야 한다.

### 4. 콘솔 스크립트

`pyproject.toml`의 `[project.scripts]`를
`planforge = "planforge.cli.main:main"`으로 바꾸고 editable 설치를 다시 실행한다.

### 5. CLI 테스트

`tests/test_cli.py`를 추가한다:

- 각 서브커맨드 `main([...])`의 stdout(핵심 문자열)과 exit code.
- `parse` 성공 0, `numcheck` red 1, `numcheck` 대상 누락 2, `derive` 설정 누락 2.
- `from planforge import __main__ as m`에서 `argparse`·`cmd_derive`가 보이는지.
- `--help`가 예외 없이 0으로 끝나는지.

기존 출력 전체를 과도하게 고정하지 말고, 기존 테스트가 이미 고정한 문자열과 겹치지
않는 범위에서 핵심만 검증한다.

## Acceptance Criteria

```powershell
backend\.venv\Scripts\python.exe -m pip install --no-build-isolation -e packages\planforge-cli
backend\.venv\Scripts\python.exe -m pytest tests\test_derive.py tests\test_cli.py -q
backend\.venv\Scripts\python.exe -m planforge --help
backend\.venv\Scripts\python.exe -m planforge parse tests\fixtures\plan.sample.md
```

## 검증 절차

1. AC를 실행한다.
2. 체크리스트:
   - 명령 이름·플래그·exit code·stdout 문자열이 동일한가?
   - `parse`/`numcheck`가 무거운 LLM 의존성을 import하지 않는가?
   - `planforge/` 웹 비의존 계약을 지켰는가?
3. `phases/refactor-standalone-cli/index.json`의 step 2를 갱신한다.

## 금지사항

- CLI 문자열·플래그·choice 순서·기본값을 바꾸지 마라. 이유: 사용자 계약이고
  `tests/test_derive.py`가 `cmd_derive`를 직접 호출한다.
- `planforge/cli/`에서 `app.*`를 import하지 마라. 이유: 웹 비의존 계약 위반이다.
- 새 콘솔 스크립트 이름을 추가하지 마라. 이유: 요청 범위는 기존 CLI 분리다.
