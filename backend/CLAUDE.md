# backend/ 개발 가이드

> **공통 계약은 저장소 루트의 `../CLAUDE.md`를 참조** — 설계 원칙(SSOT·LLM 역할 분리·
> 수치 무결성·팩트 선적립·무손실 채번·디자인 토큰 4종 세트·골격 검증)은 이 파일에서
> 반복하지 않는다. 충돌 시 루트 CLAUDE.md가 우선한다.

## 구조 (모듈러 모놀리식)

- `app/main.py` — FastAPI 앱 진입점. API 전체 목록은 `app/main.py`·OpenAPI 참조.
- `app/api.py` — 라우터 조립.
- `app/modules/` — 도메인 모듈 7종: `projects` · `sources` · `interview` · `facts` ·
  `plans` · `derivatives` · `jobs` · `review`. 새 기능은 기존 모듈을 템플릿으로 복제.
- `app/agents/` — 인터뷰 에이전트 등 에이전트 계층.
- `app/shared/` — 모듈 간 공용 코드 (`workspace.py`, `llm.py` 등).
- `planforge/` — 결정론 파이프라인 패키지: `derive.py`(plan → 파생물) ·
  `builders/{build_ppt,build_doc,theme}.py` · `numcheck.py` · `review.py` ·
  `plan/` · `llm/prompts/`(derive_{slides,report}.md).
- `app/modules/<모듈>/application/prompts/*.md` — 앱이 로드하는 런타임 LLM 프롬프트
  (interview · facts/compact · plans/plan_revise · review).

## 모듈 경계 (루트 원칙 강화)

- 타 모듈의 **테이블·내부 파일 직접 import 금지** — 반드시 대상 모듈의 `facade.py`
  공개 함수 또는 `shared/` 경유.
- `app/modules/*`에서 `planforge/` 결정론 코드를 직접 호출할 때도 모듈 facade로 우회
  하는 경로가 있는지 먼저 확인.

## 핵심 흐름 (파일 위치)

1. 프로젝트 생성 → 소스 등록 → 인터뷰 세션: 상태머신은
   `app/modules/interview/application/agent.py` + SSE 턴.
2. 팩트 적립(DB `Fact`) → plan 세대 생성 → 승인(approve).
3. derive/review job → `jobs` 테이블 + **단일 워커**(앱 lifespan asyncio 태스크 1개,
   run_job 단일 스레드 직렬). **병렬 실행 금지** — 빌더가 스레드 안전하지 않음.
   멀티 워커는 BEGIN IMMEDIATE 재설계 전까지 도입하지 않는다.
4. Plan 레코드(`Plan.markdown` = SSOT) → `app/shared/workspace.py write_plan_mirror`
   (미러 파일) → `planforge/derive.py` → `atomic_build`(원자적 빌드·채번) → Build 행.
5. 검수 → `ReviewReport`.

수정 경로는 plan revise → 새 세대 DRAFT → 재승인 → 재생성(버전 +1)만 유일하다.

## LLM 계층

- `app/shared/llm.py LLMRegistry` — 프로필(interview/derive/review)별 provider·모델을
  `PLANFORGE_CONFIG`(기본 `planforge/config.json`, gitignored)에서 읽음.
- provider는 openai SDK 기반 OpenAI 호환 단일 프로토콜. **anthropic SDK 사용 금지.**
- 테스트 주입: `create_app(llm_overrides=...)` / `JobContext(llm_overrides=...)`.

## 실행·명령

- 가상환경: `backend/.venv`.
- 서버: `uvicorn app.main:app --reload` (backend/에서).
- CLI: `python -m planforge parse|numcheck|build-ppt|build-doc|derive` (backend/에서).
- DB: `alembic upgrade head`. 기본 DB는 루트 `data/planforge.db`. 스키마 변경은
  `alembic revision`으로 마이그레이션 추가(개발용 `init_db`는 alembic 대체로만 사용).
- 타입 갱신: `python scripts/export_openapi.py` → frontend/에서 `npm run gen:types`.
- Windows: `PYTHONUTF8=1` 필수.

## 테스트

- 저장소 루트에서 `pytest` (conftest.py가 backend를 import 경로에 추가).
- 테스트별 tmp_path 임시 SQLite DB로 완전 격리 (`TEST_DATABASE_URL` 오버라이드).
- 워커 루프 비활성(`create_app(start_worker=False)`) + `run_job` 직접 호출로 job 결정론
  검증 (tests/test_jobs_worker.py 참조).
- fixture는 `tests/fixtures/`에 만든다 — `workspaces/` 아래 쓰면 SSOT 가드 훅이 차단.

## 변경 금지

- `planforge/builders/{build_ppt,build_doc,theme}.py` — legacy scripts의 바이트 동일
  이식본. **로직 변경 금지**, 경로/워크스페이스 주입만 어댑터로 처리.
- `planforge/config.json`은 gitignored(키·설정) — 커밋 대상 아님.