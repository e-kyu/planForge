# CLAUDE.md — report-agent 개발 규칙

이 저장소는 `docs/legacy/`의 Claude Code 기반 기획 문서 생성 에이전트를
Claude Code 없이 동작하는 웹 서비스로 이식하는 프로젝트다.
개발 요청서는 `AGENT-DEV-REQUEST.md`이며, 이 파일은 개발 세션 전체에서 유효한 계약을 담는다.

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
7. **디자인 토큰 4종 세트**: 색·폰트·여백 토큰 변경 시 **문서(SKILL.md)·토큰(theme.py)·
   렌더러(빌더)·샘플(samples)** 을 반드시 동시 수정. 하나만 고치는 PR은 리뷰에서 반려.
8. **골격 검증**: 파생물 생성 전 표지·목차·마무리·내용 슬라이드 각 1개 이상 검증, 미달 시 중단.

## 이식 대상 원문 (요약보다 원문이 권위 있다 — 작업 전 반드시 읽을 것)

| 원문 | 용도 |
|---|---|
| `docs/legacy/CLAUDE.md` | 전체 규칙·plan.md 포맷·report.json 스키마·버전 규칙의 원전 |
| `docs/legacy/commands/plan-doc.md` | 인터뷰 에이전트 행동 명세 (→ 백엔드 interview 단계 시스템 프롬프트) |
| `docs/legacy/commands/make-ppt.md` · `make-doc.md` | 파생물 생성 명세 (→ derive 단계 프롬프트) |
| `docs/legacy/commands/review-doc.md` | 검수 체크리스트 (→ review 단계 프롬프트) |
| `docs/legacy/commands/compact-log.md` | 팩트 압축 절차 (FR-6.1) |
| `docs/legacy/skills/SKILL.md` · `layouts.md` | 슬라이드 7종·색·폰트·좌표 + slides.json 스키마 |
| `docs/legacy/scripts/build_ppt.py` · `build_doc.py` · `theme.py` | 빌더 원형 — **로직 변경 금지, I/O 어댑터만 추가** |
| `docs/legacy/samples/*` | 계약 테스트 fixture — `tests/fixtures/`로 이식 완료 (legacy 원본은 참조용) |

## 아키텍처 개관 (M2~M4 구현 기준 — 여러 파일을 읽어야 보이는 그림)

- **파이프라인**: 프로젝트 생성 → 소스 등록 → 인터뷰 세션(상태머신 `backend/app/agents/interview.py` +
  `agents/prompts/interview.md`, SSE 턴) → 팩트 적립 → plan 세대 생성 → 승인(approve) →
  derive/review job → 단일 워커 실행 → 결정론 빌드·채번 → 검수(`ReviewReport`).
- **SSOT의 실제 구현**: plan 본문의 원본은 DB `Plan.markdown`이다. `workspace.py`
  의 `write_plan_mirror`가 워크스페이스에 `plan.md` 미러를 기록하는 것은 Deriver·빌더가
  파일로 읽는 형태일 뿐. 파생물 생성 경로는 반드시 Plan 레코드 → 미러 → Deriver
  (`reportagent/derive.py`) → 원자적 빌드(`atomic_build`) → 채번 등록(Build 행) 순서다.
- **데이터 체인 (추적성)**: `Project → InterviewSession → Fact → Plan(세대) →
  Derivative(plan_id 결합) → Build(plan_id·version_no·ext) → ReviewReport(plan_id)`.
  모든 산출물은 자신의 plan 세대를 역참조한다. 수정은 plan revise → 새 세대 DRAFT →
  재승인 → 재생성(버전 +1)만 유일한 경로다.
- **작업 큐**: `jobs` 테이블 + 단일 워커(`worker.py` — 앱 lifespan의 asyncio 태스크 1개,
  run_job은 단일 스레드 직렬). 빌더(build_ppt 모듈 전역 상태)가 스레드 안전하지 않으므로
  **병렬 실행 금지** — 멀티 워커는 BEGIN IMMEDIATE 기반 재설계 전까지 도입하지 않는다.
  시작 시 `requeue_stale_running`이 이전 프로세스의 running 잔재를 재큐잉한다.
- **LLM 계층**: `app/agents/llm.py LLMRegistry`가 프로필(interview/derive/review)별
  provider·모델을 `REPORTAGENT_CONFIG`(기본 `backend/reportagent/config.json`, gitignored —
  예시 `config.example.json`)에서 읽는다. `reportagent/llm/provider.py`는 openai SDK
  기반 OpenAI 호환 단일 프로토콜. 테스트는 `create_app(llm_overrides=...)` /
  `JobContext(llm_overrides=...)`로 fake LLM을 주입한다.
- **LLM 프롬프트 위치**: 인터뷰·검수·압축은 `backend/app/agents/prompts/*.md`(plan-doc 등
  legacy 커맨드 이식본), 파생물 변환은 `backend/reportagent/llm/prompts/derive_{slides,report}.md`.
  프롬프트 수정은 대응 legacy 원문과의 괴리를 만들지 않게 원문도 함께 볼 것.

## 개발 규칙

- 마일스톤: **M1(코어 엔진, CLI) → M2(백엔드) → M3(프론트엔드) → M4(검수·운영)**.
  현재 상태 — M1~M4 코드 완료 (2026-09-19 기준), 남은 것은 브라우저 e2e 완주.
- 빌더 포팅 시: `docs/legacy/scripts/*.py`를 `backend/`로 가져오되 로직 변경 금지,
  경로/워크스페이스 주입만 어댑터로 처리한다. 현재 `reportagent/builders/{build_ppt,
  build_doc,theme}.py`는 legacy 바이트 동일 이식본 — 로직 변경은 원칙적으로 금지.
- 테스트: `tests/fixtures/*.sample.json`이 빌더 회귀(계약 테스트)를 잠근다. 수치 무결성
  검사는 단위 테스트로 상시 실행(`/numcheck`).
- LLM 호출은 `openai` SDK 기반 provider 추상화 계층으로만 한다. anthropic SDK 사용 금지.
- Windows 개발 환경: `PYTHONUTF8=1` 필수(settings.json env에 설정됨). 파일명 금지 문자
  정규화는 legacy `_sanitize_title` 규칙을 유지한다.
- `makeReportAgent2/`는 원본 저장소의 gitignored 참조 사본 — 편집 대상 아님(권위는 `docs/legacy/`).
- 커밋 전 `git status`로 `workspaces/`·`data/`·`backend/reportagent/config.json` 등
  ignored 경로가 섞이지 않았는지 확인.

## 테스트

- 실행: 저장소 루트에서 `pytest` (conftest.py가 backend를 import 경로에 추가).
  단일 테스트: `pytest tests/test_numcheck.py::이름` 처럼 파일/노드ID로 지정.
- 앱 테스트는 테스트별 tmp_path 임시 SQLite DB로 완전 격리 (`TEST_DATABASE_URL`로 오버라이드).
- 앱 테스트는 워커 루프를 비활성(`create_app(start_worker=False)`)하고 job은 `run_job`
  직접 호출로 결정론 검증한다 (tests/test_jobs_worker.py 참조).
- 테스트 fixture는 `tests/fixtures/`에 만든다 — `workspaces/` 아래 쓰면 SSOT 가드 훅
  (`.claude/hooks/guard_ssot.py`)이 차단한다.

## 명령어

- `/kickoff` — 요청서 §8 참조 파일을 읽고 현재 마일스톤 진행 계획 제시 (새 세션 진입점)
- `/contract` — 계약 테스트(빌더 회귀) 실행
- `/numcheck` — 수치 무결성 대조 검증 실행

### 확정된 명령 (M1)

- 테스트: `pytest` (저장소 루트 — conftest.py가 backend를 import 경로에 추가)
- CLI (backend/에서 실행):
  - `python -m reportagent parse <plan.md> [--doc 문서명]` — plan 파싱·문서 필터·골격 검증
  - `python -m reportagent numcheck <plan.md> --slides <slides.json>|--report <report.json> [--doc 문서명]` — 수치 무결성 대조 (🔴 있으면 exit 1)
  - `python -m reportagent build-ppt <slides.json> [output_dir]` · `build-doc <report.json> <md|html|docx> [output_dir]` — legacy 빌더 원형 실행
  - `python -m reportagent derive <plan.md> --workspace <dir> --kind slides|report [--doc 문서명] [--fmts md html docx] [--no-build] [--allow-unconfirmed]` — LLM 변환 + 검증 게이트 + 빌드 (make-ppt/make-doc 이식). LLM 설정은 `backend/reportagent/config.json` (예시: `config.example.json`, 기본 ollama — 필요 시 프로필별 모델 지정)
- 빌더 원형: `backend/reportagent/builders/{build_ppt,build_doc,theme}.py` — docs/legacy/scripts/ 바이트 동일 이식본. 로직 변경 금지.

### 확정된 명령 (M2)

- DB: SQLite 단일 방언 (2026-09-19 전환). `alembic upgrade head` (backend/에서) — 기본
  DATABASE_URL은 저장소 루트 `data/reportagent.db`. WAL·foreign_keys=ON은 db.py 연결 리스너가 설정
- 서버: `uvicorn app.main:app --reload` (backend/에서) — 개발용 `init_db`는 alembic 대체로만 사용
- 인터뷰 SSE 턴 (text/event-stream 반환):
  - `POST /api/projects/{pid}/interview/sessions` — 세션 생성 (phase=hypothesis)
  - `POST /api/interview/sessions/{id}/kick` — 인터뷰 시작 (FR-2.2 가설 선제시)
  - `POST /api/interview/sessions/{id}/turn` — 자유 텍스트 턴
  - `POST /api/interview/sessions/{id}/answers` — 라운드 답변 (FR-2.3)
  - `POST /api/interview/sessions/{id}/facts/confirm` — 팩트 확인 게이트, 승인 시에만 적립 (FR-2.4)
  - `POST /api/interview/sessions/{id}/key-messages` — 핵심 메시지 승인 게이트 (FR-2.6)
  - `GET /api/interview/sessions/{id}/messages?after=seq` — 이력·재접속 리플레이 (D6)
- plan API:
  - `GET /api/projects/{pid}/plans` · `GET /api/plans/{id}`
  - `POST /api/plans/{id}/approve` — 승인 게이트 (FR-2.9), 이전 승인본은 superseded
  - `POST /api/plans/{id}/revise` — plan 수정 → 새 세대 DRAFT (FR-4.3)
- 인터뷰 에이전트: `backend/app/agents/interview.py` 상태머신 + `agents/prompts/interview.md` (plan-doc.md 이식). 도구 스키마는 `agents/tools.py`. 동시 턴은 프로세스 내 세션 락(409)으로 직렬화 — 단일 uvicorn 프로세스 전제.
- 소스 API (FR-2.1): `GET/POST/DELETE /api/projects/{pid}/sources` (프로젝트 소스, 검증: .md .txt .json .csv / 2MB / UTF-8 / 파일명 정규화 / 덮어쓰기 금지) + `GET /api/sources` (글로벌, 읽기전용)

### 확정된 명령 (M3)

- 프론트엔드 (frontend/에서 실행):
  - `npm run dev` — Vite 개발 서버 (/api → localhost:8000 프록시)
  - `npm run build` — tsc --noEmit + vite build
  - `npm run gen:types` — OpenAPI → TS 타입 생성 (API 계약 잠금 §3.1)
  - 타입 갱신 순서: backend/에서 `python scripts/export_openapi.py` → frontend에서 `npm run gen:types`
- 디자인 토큰: 권위는 `theme.py`. 화면용 CSS 변수 렌더는 `frontend/src/styles/tokens.css` — theme.py 변경 시 함께 수정 (원칙 7)

### 확정된 명령 (M4)

- 검수 (FR-4): `POST /api/projects/{pid}/reviews` (202 → review job), `GET /api/projects/{pid}/reviews`·`GET .../reviews/{rid}`. 결정론 검수(numcheck·문서태그·팩트 대조·세대 대응) + LLM 내용 검수 → `ReviewReport` 1건 (🔴/🟡/⚪ 카운트). LLM 내용 검수 실패는 리포트를 막지 않는다(llm_ok=false 표기).
- 검수→plan 반영 (FR-4.3): `POST /api/plans/{plan_id}/revise-from-review` (202 → plan_revise job) — 검수 리포트 발견사항(선택 indices)을 LLM이 plan에 반영 → 포맷 검증 게이트 통과 시 새 DRAFT 세대(origin=review). 수동 경로는 기존 plan 탭 revise 게이트 그대로. LLM 프로필 `plan_revise`(미설정 시 review 프로필 fallback).
- 팩트 압축 (FR-6.1): `POST /api/projects/{pid}/facts/compact` (미리보기) → `POST .../facts/compact/apply` (활성 팩트 통합 + 아카이브). 팩트 단건은 `PATCH /api/projects/{pid}/facts/{fact_id}`.
- 산출물 (FR-3.5): `GET /api/projects/{pid}/outputs` (갤러리) · `GET .../outputs/{build_id}/download` (파일 다운로드).
- job 조회: `GET /api/jobs/{job_id}` · `GET /api/projects/{pid}/jobs` — 202 수락 뒤 폴링.
- DB 스키마 변경: backend/에서 `alembic revision`으로 마이그레이션 추가(운영은 `alembic upgrade head`; 컨테이너 CMD가 기동 시 자동 실행, 개발용 `init_db`는 alembic 대체로만).
- 배포: `docker compose build && docker compose up -d` (ollama 프로필: `--profile ollama`, 최초 1회 `docker compose --profile ollama exec ollama ollama signin`). 볼륨 — workspaces/·sources/·data/. ollama 외 프로바이더는 `LLM_BASE_URL` env로 전환(`config.json`의 base_url이 더 우선).
- 토큰 변경 절차: `docs/token-checklist.md` (theme.py → SKILL.md → tokens.css 순, 원칙 7).
- 브라우저 e2e 스모크: `frontend/e2e-smoke.mjs` (node로 실행, 커밋 대상 아님 — 수동 검증 스크립트; 스크린샷은 `.e2e-shots/`).