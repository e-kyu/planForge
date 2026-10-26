# planforge-cli

PlanForge의 결정론 문서 파이프라인 엔진(plan 파서·수치 무결성 대조·검수·빌더)과
CLI를 담은 설치 가능한 독립 패키지다. 웹 백엔드(`backend/app`)와 분리되어 있으며,
FastAPI·SQLAlchemy 등 웹 의존성을 import하지 않는다.

## 설치

저장소 루트에서:

```powershell
backend\.venv\Scripts\python.exe -m pip install --no-build-isolation -e packages\planforge-cli
```

(pip 25 환경은 `setuptools`가 기본 포함되지 않으므로 먼저 `pip install setuptools`가
필요할 수 있다.)

## 실행 위치

문서화된 실행 위치는 `backend/`다 — LLM 설정 파일 `backend/planforge/config.json`을
기본 경로로 읽는다(`PLANFORGE_CONFIG` 환경변수로 재정의 가능).

## 사용법

콘솔 스크립트와 모듈 실행은 동일하다:

```powershell
planforge parse <plan.md> [--doc 문서명]
planforge numcheck <plan.md> --slides <slides.json> [--doc 문서명]
planforge build-ppt <slides.json> [output_dir]
planforge build-doc <report.json> <md|html|docx> [output_dir]
planforge derive <plan.md> --workspace <dir> --kind <slides|report> [--config 설정경로]

python -m planforge --help
```

## 설정 경로 해석 순서

`planforge derive`의 LLM 설정은 다음 순서로 찾는다:

1. `--config` 인자
2. `PLANFORGE_CONFIG` 환경변수
3. 실행 디렉토리의 `planforge/config.json` (문서화된 실행 위치가 `backend/`)
4. 패키지 디렉토리 인접 `config.json` (설치 환경 폴백)
