# backend — PlanForge 백엔드 + M1 코어 엔진

FastAPI 웹 백엔드(`app/`)와 기획 문서 생성 코어 엔진(`planforge/`)이 함께 있는
패키지다. 사용자 관점의 전체 흐름(인터뷰 → plan 승인 →
빌드 → 검수)과 설치·실행 방법은 저장소 루트 [README.md](../README.md), 개발 계약
(설계 원칙 8개)은 [CLAUDE.md](../CLAUDE.md)를 참고한다.

## 구성 개관

`backend/`는 두 레이어로 나뉜다. 웹 레이어가 코어를 **호출**하는 방향이며, 코어는
웹을 모른다(CLI로도 단독 실행 가능).

| 패키지 | 역할 | 진입점 |
|---|---|---|
| `app/` | 웹 백엔드 — REST/SSE API, SQLite DB, 작업 큐·단일 워커, 인터뷰 에이전트 | `uvicorn app.main:app --reload` (포트 8000) |
| `planforge/` | M1 코어 엔진 — plan 파싱·문서 필터·골격 검증, LLM 파생물 변환, 결정론 빌더, 수치 무결성 검사 | `python -m planforge parse\|numcheck\|derive\|build-ppt\|build-doc` |

## 디렉터리 구조

```
backend/
├── app/                          웹 백엔드 (모듈러 모놀리식)
│   ├── main.py                   create_app 팩토리 · lifespan 워커 기동 · /api/health
│   ├── api.py                    라우터 집계 — 각 모듈 presentation/api.py를 기존 계약 순서대로 포함
│   ├── modules/                  도메인 모듈 8종 — 새 기능은 기존 모듈을 템플릿으로 복제
│   │   │                         (각 모듈 공통: facade.py · presentation/{api,schemas}.py
│   │   │                          · application/ · infrastructure/models.py)
│   │   ├── projects/             워크스페이스 자동 생성 · 프로젝트 하드 삭제 (application/service.py)
│   │   ├── sources/              프로젝트 소스 업로드·삭제 + 글로벌 소스(읽기 전용 global_router)
│   │   ├── plans/                plan 세대·승인·revise (application/{service,planrevise,plan_revise_job}.py)
│   │   ├── derivatives/          파생물 생성 job + 산출물 목록·다운로드
│   │   ├── jobs/                 작업 큐 + 단일 워커 (application/worker.py)
│   │   ├── facts/                팩트 목록·수동 추가·수정·압축 (application/compact.py)
│   │   ├── interview/            인터뷰 에이전트 + SSE 턴
│   │   │                         (application/agent.py 상태머신 · domain/events.py SSE 이벤트
│   │   │                          · infrastructure/transcript.py seq 채번·이력 · prompts/interview.md)
│   │   └── review/               결정론 검수 + LLM 내용 검수 (application/{run_review,review_agent}.py)
│   ├── agents/tools.py           인터뷰 도구 5종 OpenAI function 스키마 + 서버측 검증
│   └── shared/                   모듈 간 공용 계층 (타 모듈 내부 직접 import의 유일한 우회로)
│       ├── config.py             Settings (env → 경로/DB URL 설정)
│       ├── db.py                 SQLAlchemy 엔진 (SQLite WAL·FK·busy_timeout) + Base
│       ├── errors.py             에러 핸들러 설치 (WorkspaceError/PlanError → 422)
│       ├── workspace.py          워크스페이스 규약 · plan.md 미러 · atomic_build
│       ├── llm.py                LLMRegistry — 프로필별 provider·모델 해석, chat_fn/stream_fn
│       └── types.py              공용 타입 (UTCDateTime 등)
├── planforge/                  M1 코어 엔진 (CLI 진입점)
│   ├── __main__.py               5개 서브커맨드 (parse|numcheck|derive|build-ppt|build-doc)
│   ├── derive.py                 Deriver — LLM 변환 + 검증 게이트 + 빌드 오케스트레이션
│   ├── numcheck.py               수치 무결성 대조 (plan ↔ 파생물)
│   ├── review.py                 결정론 검수 (문서 태그·팩트 대조)
│   ├── plan/                     model.py · parser.py · filter.py (문서 필터·골격 검증)
│   ├── builders/                 build_ppt.py · build_doc.py · theme.py
│   │                             (계약 테스트로 고정 — 로직 변경 금지)
│   ├── llm/                      provider.py (OpenAI 호환 단일 프로토콜)
│   │   └── prompts/              derive_slides.md · derive_report.md
│   ├── config.json               LLM 프로필 설정 (gitignored)
│   └── config.example.json       예시 설정
├── alembic/                      DB 마이그레이션 (versions/ 3개)
├── alembic.ini
├── scripts/
│   └── export_openapi.py         OpenAPI 스키마 → frontend/openapi.json 덤프
├── Dockerfile                    python:3.12-slim — CMD에서 alembic upgrade head 후 uvicorn
└── requirements.txt
```

## 아키텍처 요점

### 데이터 체인 (추적성)

```
Project → InterviewSession → Fact → Plan(세대) → Derivative → Build → ReviewReport
```

모든 산출물은 자신이 어떤 plan 세대에서 나왔는지 역참조한다. 수정은
**plan revise → 새 세대(DRAFT) → 재승인 → 재생성(버전 +1)** 만이 유일한 경로다.

### SSOT의 실제 구현

plan 본문의 원본은 DB `Plan.markdown`이다. `app/shared/workspace.py`의 `write_plan_mirror`가
워크스페이스에 기록하는 `plan.md`는 **미러**일 뿐이다 — Deriver·빌더가 파일로 읽기 위한
것. 파생 경로: `Plan` 레코드 → 미러 → `planforge/derive.py`(`Deriver`) →
`app/shared/workspace.py`의 `atomic_build` → 채번 등록(`Build` 행). `workspaces/*/work/slides.json`
등 파생물 파일에 대한 직접 쓰기는 설계상 존재하지 않는다.

### 단일 워커 (병렬 실행 금지)

- 작업 큐는 `jobs` 테이블 기반. Redis/Celery 없음. 앱 lifespan에서 asyncio 태스크
  **1개**가 `worker_loop`(1초 폴링)를 돌고, job은 `anyio.to_thread.run_sync`로
  **직렬 실행**된다.
- 이유: 빌더(`build_ppt.py`의 모듈 전역 `BLANK_LAYOUT_IDX` 등)가 스레드 안전하지 않다.
  멀티 워커는 BEGIN IMMEDIATE 기반 재설계 전까지 도입하지 않는다.
- 프로세스 시작 시 `requeue_stale_running`이 이전 프로세스의 `running` 잔재를 재큐잉한다.
- 비동기 API 3종(`revise-from-review`·`derivatives`·`reviews`)은 **202 수락 → job 폴링**
  패턴이며 job은 `GET /api/jobs/{job_id}`로 확인한다.
- 실패 job은 `error_class`(validation/schema/llm/builder/internal)로 분류된다.

### SSE 턴 (인터뷰)

- 인터뷰 턴 5종(`kick`·`turn`·`answers`·`facts/confirm`·`key-messages`)은 전부
  **POST 기반 `StreamingResponse`**(`text/event-stream`, `Cache-Control: no-cache`,
  `X-Accel-Buffering: no`).
- LLM 턴은 워커 스레드에서 실행되고 토큰 이벤트를 큐로 흘린다. blocking 도구
  (질문 카드·팩트 적립 등)가 나오면 카드/상태 이벤트를 방출하고 턴을 종료한다.
- 모든 이벤트는 동시에 `interview_messages` 행으로 영속된다. 재접속 리플레이는
  `GET .../messages?after=seq` 커서로 처리한다.
- 세션당 프로세스 내 락으로 동시 턴을 409로 직렬화한다.

## app/ 모듈 가이드

### `app/main.py`

- `create_app(llm_overrides=None, start_worker=True)` — 앱 팩토리. 테스트는
  `llm_overrides`로 가짜 LLM을 주입하고 `start_worker=False`로 워커 루프를 끈다.
- lifespan: `JobContext(session_factory, settings, llm_overrides)`를 만들어
  `worker_loop`을 기동, shutdown 시 cancel.
- CORS 미들웨어·StaticFiles 마운트 **없음** — 프론트는 Vite dev(프록시) 또는 별도
  컨테이너(nginx)로 서빙된다.
- 모듈 레벨 `app = create_app()` — `uvicorn app.main:app`용.
- `GET /api/health` → `{"status":"ok"}`.
- `init_db(engine)`: 개발용 `create_all` 헬퍼(운영은 alembic 사용).

### 모듈 구조 규약 (`app/modules/<모듈>/`)

각 도메인 모듈은 동일 레이어 구조를 가진다. 새 모듈/기능은 기존 모듈을 템플릿으로 복제한다.

| 레이어 | 역할 |
|---|---|
| `presentation/api.py` | REST·SSE 라우터 (`app/api.py`가 집계) |
| `presentation/schemas.py` | Pydantic 요청/응답 모델 (OpenAPI → 프론트 타입 원료) |
| `application/` | 도메인 로직 — 서비스·에이전트·job 핸들러·LLM 프롬프트(`prompts/*.md`) |
| `infrastructure/models.py` | SQLAlchemy 테이블 정의 (`shared/db.py`의 Base 공유) |
| `facade.py` | **타 모듈에 공개하는 함수만 모은 공개 계약** |

**모듈 경계 규칙**: 타 모듈의 테이블·내부 파일 직접 import 금지 — 반드시 대상 모듈의
`facade.py` 공개 함수 또는 `shared/` 경유. 결정·편차는 루트 `docs/architecture-decisions.md`에
기록한다.

### `app/shared/` — 공용 계층

- `config.py`: `DATABASE_URL`·`WORKSPACES_DIR`·`PLANFORGE_CONFIG`·`GLOBAL_SOURCES_DIR`·
  `SSE_KEEPALIVE_SECONDS` 환경변수를 읽는다. 기본값: DB는 저장소 루트
  `data/planforge.db`, 워크스페이스는 루트 `workspaces/`, 글로벌 소스는 루트 `sources/`.
- `db.py`: SQLAlchemy 2.x. SQLite 연결 리스너로 **WAL + foreign_keys=ON + busy_timeout
  5000**을 설정한다. URL별 엔진 캐시(`get_engine`)를 쓰고 테스트는
  `dispose_cached_engines`로 격리를 보장한다.
- `workspace.py`: 워크스페이스 규약 `workspaces/<slug>/work·output·docs·sources·assets`
  (슬러그는 ASCII 소문자-하이픈만, `validate_slug`). `write_plan_mirror`는 DB
  `plans.markdown` → `plan.md` **바이트 동일** 미러
  (`write_interview_log_mirror`·`compact_interview_log`도 동일한 미러 개념).
  소스 업로드 검증(`.md .txt .json .csv`, 2MB 이하, UTF-8, Windows 금지 문자 정규화,
  덮어쓰기 금지)과 `atomic_build`(tmp dir 빌드 → 채번 연속성 보장 복사 → `os.replace`
  원자 이동, 규약 `<문서 제목>_vNN.<ext>`는 `parse_build_filename`이 해석)도 여기 있다.
- `llm.py`: `LLMRegistry`가 프로필(interview/derive/review/plan_revise)별
  provider·모델을 `planforge/llm`에서 읽어 `chat_fn`/`stream_fn`으로 노출.
  `llm_overrides`에 있으면 가짜가 우선(테스트 주입 훅).
- `errors.py`: WorkspaceError/PlanError → 422 에러 핸들러.
- `types.py`: `UTCDateTime` TypeDecorator 등 공용 타입.

### 테이블 9개 (`modules/*/infrastructure/models.py`)

`projects` · `interview_sessions` · `interview_messages` · `facts` · `plans` ·
`derivatives` · `builds` · `jobs` · `review_reports` — 테이블 정의는 소속 도메인 모듈의
`infrastructure/models.py`로 분산되어 있다.

주요 상태 enum:
- `SessionPhase`: `hypothesis → awaiting_answers → fact_gate → key_message_gate →
  plan_review → approved` (+`failed`) — 인터뷰 상태머신의 단계.
- `PlanStatus`: `draft / approved / superseded` — 승인 시 이전 승인본이 superseded.
- `JobType`: `derive_build / review / plan_revise` · `JobStatus`: `queued/running/done/failed/cancelled`.
- 시간은 UTC 저장, enum은 value 문자열 저장(native enum 미사용).

### 작업 큐 (`modules/jobs/application/worker.py`)

- `claim_next_job` → `run_job`(동기, 핸들러 디스패치). 핸들러 3종:
  - `_derive_build`: plan 미러 갱신 → `Deriver.derive` → `atomic_build` →
    `Derivative`/`Build` 행 생성.
  - `_review`: numcheck + 세대 대응 + 문서 태그 + 팩트 대조(결정론) + LLM 내용 검수 →
    `ReviewReport`. LLM 실패는 리포트를 막지 않는다(`llm_ok=false`).
  - `_plan_revise`: LLM plan 수정 → 검증 → 새 DRAFT 세대.

### 인터뷰 에이전트 (`modules/interview/` + `app/agents/tools.py`)

- `application/agent.py`: `InterviewAgent.run_turn`이 한 POST = 한 턴. 상수
  `MAX_TOOL_TURNS=8`, `MAX_ROUNDS=8`, `PLAN_FIX_ATTEMPTS=3`. system prompt에
  `prompts/interview.md` + 소스/팩트 컨텍스트를 주입한다.
- `domain/events.py`: SSE 이벤트 팩토리 (token/done/state/notice/error).
- `infrastructure/transcript.py`: 세션별 seq 채번 + append_message (SSE 커서 겸 이력).
- `app/agents/tools.py`: 인터뷰 도구 5종(`ask_questions`·`save_facts`·
  `confirm_key_messages`·`update_checklist`·`write_plan`)의 OpenAI function 스키마와
  서버측 검증 — 라운드당 최대 4문항, 핵심 메시지는 정확히 3개.
- `facts/application/compact.py` · `plans/application/planrevise.py` ·
  `review/application/review_agent.py`: LLM은 판단/보고만 하고, 적용·검증은 결정론
  코드가 담당하는 역할 분리. plan 마크다운 검증의 단일 권위는
  `planrevise.validate_plan_markdown`(`plans/presentation/api.py`가 위임).

### LLM 프롬프트 위치

모듈별 `app/modules/<모듈>/application/prompts/*.md`
(interview·facts/compact·plans/plan_revise·review), 파생물 변환은
`planforge/llm/prompts/derive_{slides,report}.md` — 앱이 로드하는 런타임 LLM 프롬프트다.

### `app/api.py` — 엔드포인트 전체 (37개)

라우터 집계는 `app/api.py`(각 모듈 `presentation/api.py`를 계약 순서대로 포함).
전체 명세는 기동 후 http://localhost:8000/docs (Swagger).

| 영역 | Method | Path | 설명 |
|---|---|---|---|
| 헬스 | GET | `/api/health` | `{"status":"ok"}` |
| 프로젝트 | POST/GET | `/api/projects` | 생성(워크스페이스 자동 생성)/목록(status 필터) |
| | GET/PATCH/DELETE | `/api/projects/{pid}` | 조회/수정/삭제(진행 중 job 있으면 409, 팩트·plan·산출물·워크스페이스 전체 하드 삭제) |
| 소스 | GET/POST | `/api/projects/{pid}/sources` | 목록/업로드(.md .txt .json .csv, 2MB, UTF-8, 무덮어쓰기) |
| | DELETE | `/api/projects/{pid}/sources/{name}` | 삭제 |
| 글로벌 소스 | GET | `/api/sources` | 읽기 전용 목록 |
| plan | GET | `/api/projects/{pid}/plans` | 세대 목록(버전순) |
| | GET | `/api/plans/{plan_id}` | 단건 |
| | POST | `/api/plans/{plan_id}/approve` | 승인 게이트 — 이전 승인본 SUPERSEDED, plan.md 미러 갱신 |
| | POST | `/api/plans/{plan_id}/revise` | 수동 수정 → 새 DRAFT 세대(검증 실패 422) |
| | POST | `/api/plans/{plan_id}/revise-from-review` | 202 — 검수 발견사항 반영 job |
| 파생물 | POST | `/api/projects/{pid}/derivatives` | 202 — 승인 plan 대상 생성 job(승인본 없으면 409) |
| | GET | `/api/projects/{pid}/derivatives` | 파생물 목록(plan_id 필터) |
| 산출물 | GET | `/api/projects/{pid}/outputs` | 빌드 산출물(디스크 존재 재확인) |
| | GET | `/api/projects/{pid}/outputs/{build_id}/download` | 다운로드(md/html은 inline) |
| 작업 | GET | `/api/jobs/{job_id}` | job 폴링 |
| | GET | `/api/projects/{pid}/jobs` | 프로젝트 job 목록 |
| 팩트 | GET/POST | `/api/projects/{pid}/facts` | 목록(status 필터)/수동 추가 |
| | PATCH | `/api/projects/{pid}/facts/{fact_id}` | 수정 |
| | POST | `/api/projects/{pid}/facts/compact` | 압축 그룹 제안(프리뷰 — 무손실) |
| | POST | `/api/projects/{pid}/facts/compact/apply` | 승인 그룹 archive 적용 + 로그 미러 재작성 |
| 인터뷰 | POST | `/api/projects/{pid}/interview/sessions` | 세션 생성 |
| | GET | `/api/interview/sessions/{sid}` | 세션 상태(단계·게이트) |
| | GET | `/api/interview/sessions/{sid}/messages` | 트랜스크립트 + `?after=seq` 재접속 리플레이 |
| | POST | `/api/interview/sessions/{sid}/kick` | SSE — 인터뷰 시작(가설 선제시) |
| | POST | `/api/interview/sessions/{sid}/turn` | SSE — 자유 텍스트 턴 |
| | POST | `/api/interview/sessions/{sid}/answers` | SSE — 라운드 답변(선택지 카드) |
| | POST | `/api/interview/sessions/{sid}/facts/confirm` | SSE — 팩트 확인 게이트(승인 시에만 적립) |
| | POST | `/api/interview/sessions/{sid}/key-messages` | SSE — 핵심 메시지 3개 승인 |
| 검수 | POST | `/api/projects/{pid}/reviews` | 202 — 검수 job(승인 plan·파생물 없으면 409) |
| | GET | `/api/projects/{pid}/reviews` | 리포트 목록(최신순) |
| | GET | `/api/projects/{pid}/reviews/{review_id}` | 리포트 단건(findings 포함) |

## planforge/ 모듈 가이드

### CLI (`__main__.py`)

```powershell
# backend/ 에서 실행
python -m planforge parse <plan.md> [--doc 문서명]
python -m planforge numcheck <plan.md> (--slides <json> | --report <json>) [--doc 문서명]
python -m planforge derive <plan.md> --workspace <dir> --kind slides|report `
    [--doc 문서명] [--fmts md html docx] [--no-build] [--allow-unconfirmed] [--config <json>]
python -m planforge build-ppt <slides.json> [output_dir]
python -m planforge build-doc <report.json> <md|html|docx> [output_dir]
```

- `numcheck`는 red 발견 시 exit 1 (CI/훅에서 게이트로 사용).
- config 해석 우선순위: `--config` 인자 > `PLANFORGE_CONFIG` env >
  `backend/planforge/config.json`.

### `plan/` — 파서·필터·골격 검증

- `parser.py`: `parse_plan_file` / `parse_plan_text` — 결정론 파서, plan 원본을
  무변경으로 그대로 다룬다.
- `model.py`: `Slide`/`Plan`/`TableSpec`/`ChartSpec` 등 dataclass, 한글 슬라이드 유형 →
  영문 7종 매핑.
- `filter.py`: `[문서: 제안서+개발설계서]` 태그로 문서별 슬라이드 필터(`filter_slides`),
  `validate_skeleton`은 표지·목차·마무리·내용 슬라이드 각 1개 이상 검증 — 미달 시
  `SkeletonError`로 파생물 생성을 중단한다(설계 원칙 8).

### `derive.py` — Deriver

- LLM은 `write_slides_json` / `write_report_json` 도구를 각 1회 호출해 콘텐츠 변환만 한다.
- 결정론 게이트: 문서 필터 → 골격 검증 → 스키마 검증(`build_ppt.validate` /
  `build_doc.validate`) → numcheck. 수치 무결성 red가 나면 피드백을 담아 재시도
  (`MAX_ATTEMPTS=3`).
- `_snap_literals`로 차트 수치를 plan 표기대로 복원한다. 추측 수치는
  `UNCONFIRMED_MARK="(미확정"`으로 표기된다.

### `numcheck.py` / `review.py`

- numcheck: plan ↔ 파생물의 수치 토큰 다중집합 대조. Finding 코드:
  `numeric-missing/extra` · `unconfirmed-lost/extra` · `source-missing` · `structure`.
  날짜 표기는 정규화, `source` 키는 수치 풀에서 제외.
- review(결정론): `check_doc_tags`(문서 태그 어휘·골격·목차 01..NN 재채번),
  `check_facts`(팩트 수치 유실 red, `(미확정)` 해소 제안 yellow).

### `builders/` — 결정론 빌더 (로직 변경 금지)

빌더 로직은 계약 테스트(`tests/test_contract_builders.py`)가 고정하고 있다 —
**로직 변경 금지**. 경로/워크스페이스 주입만 어댑터로 처리한다.

- `build_ppt.py`: slides.json → PPTX(python-pptx). 템플릿 해석 순서:
  `meta.template` > `<프로젝트>/assets/template.pptx` > `templates/template.pptx`,
  빈 레이아웃에 배치(16:9 아니면 무시). 모듈 전역 `BLANK_LAYOUT_IDX` — **스레드
  불안전 → 단일 워커의 사유**.
- `build_doc.py`: report.json → md/html/docx. md/html은 표준 라이브러리만, docx만
  python-docx. 확장자별 독립 채번. `SECTION_TYPES={header,overview,section,conclusion}`,
  `BLOCK_KINDS={prose,table,data}`.
- `theme.py`: 디자인 토큰의 기준점. `SLIDE_W=13.333 / SLIDE_H=7.5`(16:9),
  색 `NAVY/BLUE/LIGHT_BLUE/BG/BG_SOFT/TEXT/TEXT_SUB/LINE/ACCENT`,
  `FONT="Malgun Gothic"`, 크기(`SIZE_COVER_TITLE=40` 등), 좌표(`MARGIN=0.6` 등).
  토큰 변경 시 4종 세트(theme.py·빌더 리터럴·fixture·frontend `tokens.css`)를
  동시 점검해야 한다 — 절차는 `docs/token-checklist.md`.

### `llm/` — provider 추상화

- `provider.py`: **OpenAI 호환 단일 프로토콜**만 지원(openai SDK). anthropic SDK
  사용 금지. ollama·openai를 base_url/키 차이만으로 소화한다(ollama는 더미 키 `ollama`).
- `PROFILES=("interview","derive","review")` + `plan_revise`. 프로필별
  `provider/model/base_url/api_key_env`.
- base_url 우선순위: config `base_url` > `LLM_BASE_URL` env > provider 기본값
  (ollama `http://localhost:11434/v1`, openai API 기본).
- 타임아웃: `REQUEST_TIMEOUT=600`, `STREAM_DEADLINE=900`(정체 스트림 강제 중단).
- 프롬프트: `llm/prompts/derive_slides.md`(plan→slides.json),
  `llm/prompts/derive_report.md`(plan→report.json — 문장체 재구성 + 수치 무결성 규칙).
  앱 측 프롬프트는 모듈별 `app/modules/<모듈>/application/prompts/*.md`에 별도로 있다.

### LLM 설정 (`config.json`, gitignored)

```json
{
  "profiles": {
    "interview":   { "provider": "ollama", "model": "gemma4:26b" },
    "derive":      { "provider": "openai", "model": "gpt-4.1" },
    "review":      { "provider": "openai", "model": "gpt-4.1" },
    "plan_revise": { "provider": "openai", "model": "gpt-4.1" }
  }
}
```

`model`은 필수. `config.example.json`을 복사해 시작한다. **Ollama 모델은 tool calling
지원이 필수**다.

## 데이터베이스·마이그레이션

- SQLite 단일 방언. 기본 파일은 저장소 루트 `data/planforge.db`(WAL 파일 동반).
- 스키마 변경은 반드시 `alembic revision`으로 마이그레이션을 추가한다:

  ```powershell
  cd backend
  alembic upgrade head      # 적용
  alembic revision -m "..." # 새 마이그레이션
  ```

- `alembic/env.py`는 `DATABASE_URL` env → `app/shared/config.py get_settings().database_url`
  폴백이며 SQLite batch mode(`render_as_batch=True`)를 쓴다.
- 현재 리비전 3개: `22d6dcbe6fee`(initial M2 tables) → `663e20e95505`(review_reports) →
  `c7e8d4a2f19b`(add updated_at).
- 배포 컨테이너는 CMD에서 `alembic upgrade head`를 기동 시 자동 실행한다.
  개발용 `init_db`는 alembic 대체로만 사용.

## 환경변수

| 변수 | 위치 | 기본값 |
|---|---|---|
| `DATABASE_URL` | `app/shared/config.py` · `alembic/env.py` | 저장소 루트 `data/planforge.db` |
| `WORKSPACES_DIR` | `app/shared/config.py` | 저장소 루트 `workspaces/` |
| `GLOBAL_SOURCES_DIR` | `app/shared/config.py` | 저장소 루트 `sources/` |
| `PLANFORGE_CONFIG` | `app/shared/config.py` · CLI | `backend/planforge/config.json` |
| `SSE_KEEPALIVE_SECONDS` | `app/shared/config.py` | 15 |
| `LLM_BASE_URL` | `planforge/llm/provider.py` | — (config base_url 다음 우선순위) |
| `OPENAI_API_KEY` | `provider.py` | provider가 openai일 때 필수(프로필별 `api_key_env`로 이름 지정 가능) |
| `PYTHONUTF8=1` | Dockerfile · compose | Windows에서 필수 |
| `TEST_DATABASE_URL` | `tests/conftest.py` | 테스트 DB 격리 오버라이드 |

`.env`/dotenv 지원은 없다 — 설정은 순수 OS 환경변수로만 들어오며(개발 셸 또는
docker-compose `environment`), 요구사항은 `requirements.txt`의 floor-pin(`>=`)만 있다.

## 실행

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy planforge\config.example.json planforge\config.json   # LLM 프로필 설정
alembic upgrade head                                            # DB 스키마 생성
uvicorn app.main:app --reload                                   # http://localhost:8000
```

Docker 배포는 루트 [README.md §3](../README.md#3-빠른-시작-docker-compose--권장) 및
루트의 `docker-compose.yml` 참고 — 컨테이너 CMD가 `alembic upgrade head` 후 uvicorn을
띄우고, API와 인프라 워커가 한 프로세스에서 동작한다.

## 테스트

테스트는 저장소 루트 `tests/`에 있다(루트 conftest가 `backend/`를 import 경로에 추가).

```powershell
# 저장소 루트에서
pytest
pytest tests/test_numcheck.py::테스트이름   # 단일 지정
```

주요 패턴:
- 테스트별 tmp_path 임시 SQLite로 완전 격리(`TEST_DATABASE_URL`로 오버라이드).
- 워커 루프 비활성(`create_app(start_worker=False)`) — job은
  `JobContext(..., llm_overrides={...})`를 만들어 `claim_next_job` + `run_job`
  **직접 호출**로 결정론 검증.
- LLM은 `tests/fakes.py`의 `FakeLLM`/`FakeStreamLLM`을 `llm_overrides`로 주입.
- SSE는 TestClient로 스트림을 수집하고, `tests/fixtures/`의 샘플
  (`plan.sample.md` · `slides.sample.json` · `report.sample.json` 등)이 계약 테스트의
  동일성을 잠근다.
- `tests/test_alembic_upgrade.py`는 `upgrade → downgrade → upgrade` 사이클을
  subprocess로 검증한다.

## OpenAPI → 프론트 타입 동기화

API 스키마가 바뀌면 타입을 재생성한다:

```powershell
cd backend
python scripts/export_openapi.py     # → frontend/openapi.json 덤프
cd ../frontend
npm run gen:types                    # openapi-typescript로 TS 타입 생성
```

`scripts/export_openapi.py`는 `create_app(start_worker=False)`로 스키마만 뽑는다.

## 개발 시 주의사항

- **빌더 로직 변경 금지** — `planforge/builders/*`는 계약 테스트가 고정한 결정론 빌더다.
  경로/워크스페이스 주입만 어댑터로 처리.
- **LLM은 콘텐츠 변환만** — 파일 조립·좌표 배치·채번은 결정론 코드. LLM이 pptx/docx
  바이너리를 만드는 코드는 금지.
- **anthropic SDK 금지** — LLM 호출은 openai SDK 기반 provider 추상화 계층으로만.
- **멀티 워커 금지** — 빌더의 모듈 전역 상태 때문에 병렬 실행은 사양 위반이다.
- **커밋 전 `git status`** — `workspaces/`·`sources/`·`data/`·`config.json` 등
  ignored 경로가 섞이지 않았는지 확인.
- 스키마 변경은 반드시 alembic 리비전으로; `init_db`는 개발용 대체일 뿐.