# 아키텍처 결정 기록 — `default_architecture_guidelines.md` 적용 (2026-09-23)

`sources/default_architecture_guidelines.md`(v1.0, Modular Monolith + React Feature-driven MVVM)를
PlanForge 코드베이스에 적용하며 내린 결정과 **가이드 대비 편차·해석**을 기록한다.

적용 동기: Claude Code 같은 AI 에이전트가 기능 작업 시 **필요한 모듈·feature만 읽고 수정**해
토큰을 절약하고 가독성을 높인다. 구조적 재구성을 실행 대상으로 삼았다(문서화만 하는 수동 접근 기각).

## 채택 결정 (가이드 그대로)

| 결정 | 근거 | 내용 |
|---|---|---|
| D-1 모듈러 모놀리식 | §1.1, §1.2 | `app/modules/{projects,interview,facts,plans,derivatives,review,jobs,sources}` 8 모듈 + `app/shared` + `app/agents`(공용 에이전트 인프라 잔존) + `app/main.py` |
| D-2 모듈 경계 | §1.1.2, §4.2 | 모듈 간 접근은 대상 모듈 `facade.py` 공개 함수로만. 타 모듈 테이블·내부 파일 직접 import 금지 — `facade`/`shared` 경유. 예: 인터뷰 퍼사드의 팩트 적립은 `facts.facade.add_fact()`, plan 승인의 잡 큐잉은 `jobs.facade.enqueue()`, `delete_project`는 각 모듈 퍼사드의 삭제 함수를 순차 호출 |
| D-3 계층 배치 | §1.2 | `presentation/`(api·schemas) · `application/`(유스케이스·에이전트) · `infrastructure/`(models·workspace fs) · `domain/`(순수 규칙·이벤트). DB 테이블 없는 sources 모듈은 facade+presentation만 |
| D-4 모듈 데이터 소유 | §5.2 | `models.py` 해체 → 모듈별 `infrastructure/models.py`. 단일 `Base`는 `shared/db.py` 유지, alembic env에서 모듈 models 일괄 import — 마이그레이션 히스토리 불변 |
| D-5 공통 컬럼 | §5.3 | 전 테이블 `created_at`은 기존 존재, `updated_at` 신설 — `shared/types.py UpdatedAtMixin`(nullable, `onupdate=func.now()`) + alembic revision 1개. Pydantic 스키마에 노출하지 않아 계약 불변 |
| D-6 오류 응답 단일 스키마 | §5.1 | `shared/errors.py` — `{"detail", "code"}` 병행. `code: not_found\|conflict\|validation_error\|request_validation`. `detail` 유지로 프론트 계약 하위호환 |
| D-7 삭제 정책 단일 채택 | §5.3 | **물리 삭제** 유지(기존 `delete_project` 사슬 — 자식→부모 순서, SQLite FK ON, 파일은 커밋 후 삭제). 소프트 삭제 미도입 |
| D-8 스키마 관리 | §5.4 | Alembic 유지 — 수동 DDL 금지. 신규 revision: `updated_at` ADD COLUMN(nullable — SQLite 상수 기본값 제약 회피) |
| D-9 Feature-driven MVVM | §2 전면 | `features/{projects,project,interview,sources,plan,outputs,review}` 각 `models/`(API 호출) + `viewmodels/`(훅) + `views/`(표현). 서버 상태는 **TanStack Query** — GET `useQuery`, 갱신 `useMutation`+무효화. 반복되던 `useEffect+apiGet+setError` 패턴이 viewmodel 훅 1개로 수렴 |
| D-10 MVVM 엄수 | §4.3 | View는 표현만 — fetch·서버 데이터 동기화 로직을 View에 두지 않는다. 단일 GET도 viewmodel 훅 경유(예외 없음 — 패턴 일관성 우선) |
| D-11 모듈러 퍼사드 vs 외부 Facade 구분 | §1.1 vs §3.1 | 모듈 간은 §1.1 모듈 퍼사드, 외부 시스템(LLM provider)은 §3.1 Facade 성격의 기존 `shared/llm.py LLMRegistry` 유지 |
| D-12 컨테이너 단일 배포 | §6.3 | docker compose 단일 이미지(모놀리식과 일관) — 변경 없음 |

## 편차·해석 (가이드 예시를 PlanForge에 치환)

1. **빌더 미변경** — `planforge/builders/*`는 legacy 스크립트의 바이트 동일 이식본(CLAUDE.md 원칙).
   모듈러 재구성은 `app/` 웹 계층에만 적용. `derivatives` 모듈이 어댑터로 경로·워크스페이스를 주입한다.
   → `planforge/` 엔진 패키지는 웹 비의존(app→planforge 단방향) 원칙도 그대로.
2. **Protocol→팩토리 유지** — §3.2 Strategy(DI 클래스) 대신 기존 팩토리 함수(`LLMRegistry`,
   `create_app(llm_overrides=)` / `JobContext(llm_overrides=)`) 유지. 테스트 주입 지점이 이미
   팩토리 인자로 확립돼 있어 추상화 레이어 추가는 §4.1(Pragmatic) 위반이다.
3. **도메인 이벤트 미도입** — §1.1.3은 "선택". 현재 결합은 동기 퍼사드 호출 + 단일 워커 직렬로 충분
   → 인프로세스 디스패처도 도입하지 않음. 트래픽·일관성 요건 확인 시 재검토.
4. **§4.3 "useEffect 격리"의 해석** — **데이터 효과**(fetch, 쿼리 폴링·무효화, 복원 정리)는 viewmodel로;
   **DOM/UI 효과**(채팅 스크롤, Esc 키 리스너, 토글 포커스 이동)는 View에 잔존. 후자는 표현 관심사로
   viewmodel로 옮기면 오히려 렌더 컨텍스트와 결합된다. 데이터/표현 효과 구분이 이 결정의 핵심.
5. **SSE 스트림은 query 캐시 밖** — 인터뷰 턴은 POST→SSE 계약(D6). 스트림 소비(apiSSE)는
   `useInterview` 훅 안에서 직접 관리하고, token 버퍼는 로컬 상태. 종료(done) 후
   세션·이력·팩트 쿼리를 무효화해 다시 당겨온다(**이력이 권위**, 스트림은 표시 보조).
6. **HeaderMetrics를 `features/project/views`로 이동** — 헤더 메트릭은 프로젝트 데이터(10초 폴링)에
   의존하므로 shared에 두면 shared→features 역방향 import가 된다. 의존 방향 준수가 재사용성보다 우선.
   헤더는 표현만 하고 데이터는 `useHeaderMetrics`가 보유.
7. **viewmodel 1개당 쿼리 여러 개 허용** — `useHeaderMetrics`는 3개 GET을 `Promise.allSettled`로
   묶어 부분 실패 시 "—" 표시로 살아남는다(원본 동작 유지). 탭 배지는 `staleTime: Infinity`로
   마운트 1회 수집(원본 동작), 잡 폴링은 `refetchInterval` 조건 함수로 대체(활성 잡 없으면 폴링 정지).
8. **events/transcript 배치** — `interview/domain/events.py`(SSE 이벤트 정의), `interview/infrastructure/transcript.py`(이력 저장) — 각각 규칙과 I/O로 분류.
9. **openapi 계약 불변 증명** — 재구성 전후 `export_openapi.py` 산출물 `git diff` 0. 프론트
   `types.gen.ts`는 재생성 불필요. 단, 계약 파일 갱신 시에는 시스템 python(fastapi 0.115.x 계열)으로
   export한다 — venv의 신버전 라이브러리는 UploadFile/ValidationError 렌더링이 달라져 diff가 발생한다
   (환경 고정 요건, 위 "계약 export 환경" 참조).
10. **LLM 트랜스포트: openai SDK 직접 사용 → langchain-openai 어댑터** (2026-09-25, `new-arc-langgraph`)
    - 대상 계약: `planforge/llm/provider.py` 상단 명세(AGENT-DEV-REQUEST.md §3.1)를 **의도적으로 변경**한다.
      유지되는 하위 계약: OpenAI 호환 단일 프로토콜(ollama/openai를 base_url·키 차이만으로 소화),
      anthropic SDK 금지, 프로필(interview/derive/review/plan_revise)별 모델 지정, API 키는 서버
      환경변수로만 관리.
    - 변경: `OpenAICompatProvider` 내부를 `langchain-openai ChatOpenAI` 호출로 교체.
      `chat_fn`/`stream_fn` 계약(OpenAI 프로토콜 dict ↔ provider 이벤트 dict)은 불변 — dict↔LangChain
      메시지 변환은 provider 내부에만 존재하고, 호출 사이트·테스트 fake(`FakeLLM`/`FakeStreamLLM`)
      는 전혀 바뀌지 않는다. `max_retries=0`으로 자동 재시도 금지 계약을 유지한다.
    - 근거: (1) 인터뷰 도구 루프를 langgraph StateGraph로 표준화(`turn_graph.py`) (2) 스트리밍·도구
      델타 누적·타임아웃 구현 재사용 (3) provider 확장 지점이 langchain 생태계로 열림.
    - 미채택: `create_react_agent` 등 langgraph 프리셋 — 도구 판정·게이트·검증·커밋은 서버 코드
      권한(설계 원칙 2). 그래프는 턴 1건당 1회 invoke, checkpointer 없음(세션 상태는 DB가 SSOT).
    - D-11·편차 2 재확인: `LLMRegistry` 팩토리와 `create_app(llm_overrides=...)`/
      `JobContext(llm_overrides=...)` 주입 지점 불변, 위에 추상화 레이어 추가 없음.
    - 동반 수정: `PROFILES`에 `plan_revise` 누락 버그(`load_config`이 드랍 → review 폴백) 해소.

11. **LLM 도구 루프 표준화: 수제 루프 4곳 → LangGraph 공용 tool-loop 그래프** (2026-09-25, `new-arc-langgraph`)
    - 편차 10에서 인터뷰 턴 루프만 StateGraph로 표준화하고 derive를 "비변경"으로 명시했으나,
      검사 결과 남은 LLM 루프 4곳이 동일 패턴 — "chat_fn 호출 → 도구 누락이면 nudge /
      검증 실패면 tool 피드백 쌍으로 재시도 / 통과면 결과" — 으로 수제 구현돼 있어 이 결정으로 갱신한다.
    - 변경: `planforge/llm/loops.py::run_tool_loop`(공용 StateGraph 팩토리)로 표준화.
      대상: `planforge/derive.py::Deriver._run_llm`(스키마·numcheck 재시도, ≤3),
      `plans/application/planrevise.py::run_plan_revise`(포맷 재시도, ≤3),
      `review/application/review_agent.py::run_llm_review`(nudge, ≤2),
      `facts/application/compact.py::run_llm_compact`(nudge, ≤2).
    - 그래프는 제어 흐름만 표준화 — 판정·피드백 문구는 caller의 `validate` 클로저
      (결정론 코드)가 담당한다. LLM/코드 역할 분리(원칙 2)·프리셋 에이전트 미채택은
      편차 10과 동일 근거. `create_react_agent` 미채택, checkpointer 없음.
    - 불변: `run_*`/`derive()` 시그니처·반환값, 오류 메시지·피드백 문구, 메시지 조립
      순서(테스트 `llm.calls[N][-1]` 고정), attempts 의미(총 chat_fn 호출 횟수 —
      도구 누락 nudge도 1 attempt 소비), 도구 피드백 프로토콜(assistant.tool_calls →
      tool 쌍 — ollama cloud 무응답 사고 대응, 이식 유지), fake·`chat_fn` dict 계약.
    - 배치: `planforge/llm/` — provider가 이미 langchain-openai를 쓰므로 엔진이
      langgraph를 갖는 것과 일관. CLI(`python -m planforge derive`)도 동일 경로,
      app 모듈의 planforge import는 app→planforge 단방향 위반이 아니다.

12. **interview `progress` 이벤트: emit-only(미영속) — 턴 내부 진행과 세션 페이즈(state)의 의미 분리** (2026-09-25, `new-arc-langgraph`)
    - 배경: POST /kick 이후 첫 토큰까지의 지연(컨텍스트 조립·LLM TTFB·도구 라운드 갭) 동안
      채팅창에 진행 표시가 없다. 기존 `state` 이벤트는 컨텍스트 조립이 끝난 뒤 방출되어
      가장 긴 구간을 커버하지 못하고, 페이로드는 세션 페이즈라 턴 내부 진행 표현이 불가하다.
    - 결정: `domain/events.py::progress_event(step: context|llm|tool)` — `run_turn` 시작(컨텍스트
      조립 직전), `turn_graph`의 `call_llm`/dispatch 노드 시작에서 방출. 문구 매핑은 프론트
      (`InterviewPanel.tsx PROGRESS_LABEL`) 소유.
    - emit-only(미영속) 근거: progress는 수명이 턴 안에서 끝나는 휘발 UI 상태. 영속 시
      GET /messages 리플레이에 "…하는 중" 행이 쌓여 이력이 오염되고 seq 커서(after=seq)를
      소비한다. 기존 `state_event` 방출(agent.py)도 실제로는 emit-only 패턴 — 이를 확장한 것.
      events.py의 "모든 이벤트 영속" docstring은 이벤트별 수동 `_append`가 원칙임을 전제한다.
    - 불변: state/token/카드 이벤트의 기존 방출 순서·페이로드, `MessageKind` enum(신규 kind 없음),
      OpenAPI 계약(SSE는 스키마 밖이라 `types.gen.ts` 재생성 불필요), 턴 루프 그래프 구조
      (노드·엣지 추가 없음 — 기존 노드 안에 emit 1줄씩).

## 토큰 효율 (적용 목적의 정량화)

- 기능 수정 시 읽는 범위: 이전 — `models.py`(9 테이블 전부)·`api/<domain>.py`·`pages/*.tsx` 통째.
  이후 — 해당 모듈의 `application/`+`infrastructure/models.py`(+필요 시 facade), 프론트는 해당 feature
  3개 파일만. 예: 팩트 압축 수정 = `facts/application/compact.py` + `facts/presentation/*` +
  `features/interview/viewmodels/useCompact.ts`.
- 신규 기능 추가 템플릿: 모듈 5계층 복제 / feature 3폴더 복제(기준 패턴: interview).

## 배포·롤백 (§6.3–6.4)

- **배포**: `docker compose build && docker compose up -d` — 단일 이미지(§6.3). 스키마 변경은
  컨테이너 기동 전 `alembic upgrade head`.
- **롤백 절차**: 이전 이미지 태그 재배포(`docker compose`에서 이전 태그 지정) → DB는
  `alembic downgrade -1` 한 단계만 허용(`updated_at`은 nullable 추가 컬럼이라 구 버전 코드와
  공존 가능 — 이것이 롤백 안전성의 근거).
- **롤백 기준**: 핵심 시나리오(프로젝트 생성 → 인터뷰 완주 → plan 승인 → 파생물 생성 → 검수) 중
  하나라도 실패, 또는 5xx 오류율 임계(예: 5분 창 5%) 초과.
- **계약 불변 원칙**: 롤백 후에도 openapi.json·`types.gen.ts`가 이전과 동일함이 전제 — 이번 재구성은
  API 경로·스키마를 전혀 바꾸지 않았다(위 증명).

## 계약 export 환경 (주의)

`python scripts/export_openapi.py`(backend/에서, 시스템 python)로 export한 결과가 커밋 계약이다.
`backend/.venv`의 fastapi/pydantic 신버전은 `UploadFile`을 `contentMediaType: application/octet-stream`으로,
ValidationError에 `input`/`ctx`를 추가로 렌더링한다 — venv로 export하면 계약 diff가 발생한다.
venv를 의도적으로 업그레이드했다면 별도 커밋에서 계약을 재생성·커밋할 것(프론트 `npm run gen:types` 동반).