# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# PlanForge 개발 규칙

이 저장소는 Claude Code 기반 기획 문서 생성 에이전트(docs/legacy, 원문은 git 이력에만
존재)를 Claude Code 없이 동작하는 웹 서비스로 이식한 프로젝트다.
개발 요청서는 `AGENT-DEV-REQUEST.md`(압축판)이며, 이 파일은 개발 세션 전체에서 유효한 계약을 담는다.

## 설계 원칙 계약 (AGENT-DEV-REQUEST.md §2.1 — 위반 시 구현 자체가 오답)

1. **SSOT**: 콘텐츠의 유일한 원본은 plan.md(DB `Plan` 레코드)다. 파생물
   (slides.json·report.json·산출물)은 절대 직접 수정하지 않고 항상 원본에서 재생성한다.
   `workspaces/*/work/slides.json`, `work/report.json`, `workspaces/*/output/*`에 대한
   직접 쓰기/편집은 PreToolUse 훅(`.claude/hooks/guard_ssot.py`)이 차단한다 — 훅을
   우회할 방법을 만들지 말고, 차단 메시지를 보면 설계를 되돌아볼 것.
2. **LLM/코드 역할 분리**: LLM은 콘텐츠 변환만 한다. 파일 조립·좌표 배치·채번은
   Python 빌더(결정론)가 담당한다. LLM이 pptx/docx 바이너리를 만드는 코드는 금지.
3. **수치 무결성**: 수치·표·차트 데이터·`(미확정)` 표기·근거/출처 문자열은 plan과
   한 글자도 다르게 복사되지 않는다. 재구성(개조식→서술형)은 문장에만 적용.
4. **팩트 선(先)적립**: 확정 팩트는 먼저 팩트 저장소(DB `Fact`)에 기록 후 plan 반영.
   추측 수치는 `(미확정)` 명시.
5. **무손실 채번**: 산출물명 `<문서 제목>_vNN.<ext>`, 확장자별 독립 시퀀스, 절대 덮어쓰기
   금지(동시성 포함 — 빌드는 DB 작업 큐로 직렬화).
6. **다중 문서 태그**: `[문서: 제안서+개발설계서]` 태그로 문서별 필터링, 문서별 목차 재채번.
7. **디자인 토큰 4종 세트**: 색·폰트·여백 토큰 변경 시 **토큰(theme.py)·렌더러(빌더)·
   계약 fixture(tests/fixtures/*.sample.json)·프론트 미러(tokens.css)** 를 반드시 동시
   점검·수정 — 좌표 규격 변경이면 fixture 갱신 (절차: `docs/token-checklist.md`).
   하나만 고치는 PR은 리뷰에서 반려.
8. **골격 검증**: 파생물 생성 전 표지·목차·마무리·내용 슬라이드 각 1개 이상 검증, 미달 시 중단.

## 아키텍처 요점

**구조**: 가이드(`sources/default_architecture_guidelines.md`) 적용 — 백엔드 모듈러 모놀리식
(§1), 프론트엔드 feature-MVVM(§2). 결정·편차 기록: `docs/architecture-decisions.md`.
**모듈 경계 규칙**: 타 모듈의 테이블·내부 파일 직접 import 금지 — 반드시 대상 모듈의
`facade.py` 공개 함수 또는 `shared/` 경유. 새 모듈/기능은 기존 모듈·feature를 템플릿으로 복제.

- **파이프라인**: 프로젝트 생성 → 소스 등록 → 인터뷰 세션(상태머신
  `backend/app/modules/interview/application/agent.py` + SSE 턴) → 팩트 적립 → plan 세대 생성 →
  승인(approve) → derive/review job → 단일 워커 실행 → 결정론 빌드·채번 → 검수(`ReviewReport`).
- **SSOT의 실제 구현**: plan 본문의 원본은 DB `Plan.markdown`이다. `app/shared/workspace.py`의
  `write_plan_mirror`가 워크스페이스에 기록하는 `plan.md`는 Deriver·빌더가 파일로 읽는
  미러일 뿐. 파생 경로: Plan 레코드 → 미러 → Deriver(`planforge/derive.py`) → 원자적
  빌드(`atomic_build`) → 채번 등록(Build 행).
- **데이터 체인 (추적성)**: `Project → InterviewSession → Fact → Plan(세대) →
  Derivative → Build → ReviewReport`. 모든 산출물은 자신의 plan 세대를 역참조한다.
  수정은 plan revise → 새 세대 DRAFT → 재승인 → 재생성(버전 +1)만 유일한 경로다.
- **작업 큐**: `jobs` 테이블 + 단일 워커(앱 lifespan의 asyncio 태스크 1개, run_job 단일
  스레드 직렬). 빌더가 스레드 안전하지 않으므로 **병렬 실행 금지** — 멀티 워커는
  BEGIN IMMEDIATE 기반 재설계 전까지 도입하지 않는다. 시작 시 `requeue_stale_running`이
  이전 프로세스의 running 잔재를 재큐잉한다.
- **LLM 계층**: `app/shared/llm.py LLMRegistry`가 프로필(interview/derive/review/plan_revise)별
  provider·모델을 `PLANFORGE_CONFIG`(기본 `backend/planforge/config.json`, gitignored —
  예시 `config.example.json`)에서 읽는다. provider는 `langchain-openai ChatOpenAI`
  기반 OpenAI 호환 단일 프로토콜(아키텍처 결정 편차 10 — chat_fn/stream_fn dict 계약은 불변).
  인터뷰 턴 루프는 langgraph StateGraph(`interview/application/turn_graph.py`), 도구 루프
  (derive 재변환·plan_revise·review·compact)는 공용 StateGraph
  (`planforge/llm/loops.py run_tool_loop` — 편차 11). 테스트는
  `create_app(llm_overrides=...)` / `JobContext(llm_overrides=...)`로 fake LLM을 주입한다.
- **프롬프트 위치**: 모듈별 `backend/app/modules/<모듈>/application/prompts/*.md`
  (interview·facts/compact·plans/plan_revise·review), 파생물 변환은
  `backend/planforge/llm/prompts/derive_{slides,report}.md` — 앱이 로드하는
  런타임 LLM 프롬프트다.
- **프론트엔드**: React 19 + TypeScript(Vite), 자체 CSS + TanStack Query. `src/features/`
  에 화면별 feature 7종 — 각 `models/`(API 호출)·`viewmodels/`(상태·로직 훅)·`views/`
  (표현 전용 컴포넌트). `shared/components/`에 CodeMirror 에디터·마크다운 미리보기·공통 UI,
  `shared/lib/`에 라우터·에러 문자열 변환. **View에 fetch·서버 데이터 로직 금지 —
  viewmodel 훅 경유(가이드 §4.3)**. API 타입 `src/api/types.gen.ts`는 `npm run gen:types`로
  갱신하는 자동 생성물이다.

## 개발 규칙

- 상태: **M1~M4 코드 완료 (2026-09-19)**. 남은 것: 브라우저 e2e 완주.
- 빌더 `backend/planforge/builders/{build_ppt,build_doc,theme}.py`는 legacy scripts의
  바이트 동일 이식본 — **로직 변경 금지**, 경로/워크스페이스 주입만 어댑터로 처리.
- LLM 호출은 `langchain-openai` ChatOpenAI 기반 provider 어댑터 계층으로만 한다
  (`chat_fn`/`stream_fn` dict 계약 유지). anthropic SDK 사용 금지.
- Windows 개발 환경: `PYTHONUTF8=1` 필수(settings.json env). 파일명 금지 문자 정규화는
  legacy `_sanitize_title` 규칙 유지.
- 커밋 전 `git status`로 `workspaces/`·`sources/`·`data/`·`backend/planforge/config.json`
  등 ignored 경로가 섞이지 않았는지 확인.
- 도구 설정: 저장소 `.ignore`(ripgrep)가 `frontend/openapi.json`·`package-lock.json`·
  이미지 바이너리를 Grep/Glob 콘텐츠 검색에서 제외한다. `.claude/settings.json`은
  `backend/planforge/config.json`·`data/**`·`.env*`의 Read/Edit를 deny한다(키·DB 보호).

## 테스트

- 실행: 저장소 루트에서 `pytest` (conftest.py가 backend를 import 경로에 추가).
  단일 테스트는 `pytest tests/test_numcheck.py::이름` 처럼 파일/노드ID로 지정.
- 프론트 타입 체크·빌드: frontend/에서 `npm run build` (`tsc --noEmit` 포함 — lint 설정은 없음).
- 브라우저 e2e 스모크: 양쪽 dev 서버(backend 8000 + frontend 5173) 기동 후 frontend/에서
  `node e2e-smoke.mjs` — 실제 LLM을 호출하는 수동 검증 스크립트(커밋 대상 아님),
  스크린샷은 `.e2e-shots/`에 쌓인다. `visual-smoke.mjs`는 임시 리스타일 확인용.
- 앱 테스트는 테스트별 tmp_path 임시 SQLite DB로 완전 격리 (`TEST_DATABASE_URL`로 오버라이드).
- 앱 테스트는 워커 루프를 비활성(`create_app(start_worker=False)`)하고 job은 `run_job`
  직접 호출로 결정론 검증한다 (tests/test_jobs_worker.py 참조).
- 테스트 fixture는 `tests/fixtures/`에 만든다 — `workspaces/` 아래 쓰면 SSOT 가드 훅
  (`.claude/hooks/guard_ssot.py`)이 차단한다.

## 명령어

- 가상환경: `backend/.venv` (`.vscode/settings.json`이 인터프리터로 지정).
- 슬래시: `/kickoff`(세션 진입점) · `/contract`(계약 테스트) · `/numcheck`(수치 무결성)
- CLI (backend/에서): `python -m planforge parse|numcheck|build-ppt|build-doc|derive ...`
- DB: backend/에서 `alembic upgrade head` — 기본 DB는 루트 `data/planforge.db`.
  스키마 변경은 `alembic revision`으로 마이그레이션 추가(개발용 `init_db`는 alembic 대체로만).
- 서버: `uvicorn app.main:app --reload` (backend/) · `npm run dev` (frontend/, /api 프록시)
- 타입 갱신: backend/ `python scripts/export_openapi.py` → frontend/ `npm run gen:types`
- API 전체 목록은 `backend/app/main.py`·OpenAPI 참조.
- 배포: `docker compose build && docker compose up -d`
- 토큰 변경 절차: `docs/token-checklist.md` (원칙 7)