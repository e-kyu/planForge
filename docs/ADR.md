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

13. **프로바이더 추가: azure — AzureChatOpenAI 어댑터 분기** (2026-09-30)
    - 배경: 사내 Azure OpenAI 게이트웨이(`azure_endpoint` + `api_version` + 배포명 기반)로
      LLM 호출을 전환해야 한다. `ChatOpenAI`에게는 `azure_endpoint`를 표현할 방법이 없고,
      `AzureChatOpenAI.validate_base_url`이 base_url 경유 전달을 ValueError로 거부한다.
    - 변경: `ProfileConfig`에 `azure_endpoint`·`api_version` 필드 추가,
      `OpenAICompatProvider.__init__`가 `provider == "azure"`에서
      `AzureChatOpenAI(model, azure_deployment=model, azure_endpoint, api_version, api_key,
      timeout, max_retries=0)`로 분기. api_key_env 기본값 azure는 `AZURE_OPENAI_API_KEY`.
      `config.example.json`을 azure 기준으로 전환(엔드포인트는 플레이스홀더).
    - 계약 유지: `AzureChatOpenAI`는 `ChatOpenAI`와 동일 `BaseChatOpenAI` 계열 —
      `chat_fn`/`stream_fn` dict 계약·`bind_tools(tool_choice="auto")`·`tool_call_chunks`
      조립·deadline 중단 로직 무변경. `max_retries=0`(자동 재시도 금지)도 동일 적용.
      langchain-openai 안(동일 패키지 — `requirements.txt` exact-pin 불변), anthropic SDK 금지 유지.
    - 명시 실패: `azure_endpoint`/`api_version`/키 누락은 provider 생성기에서 한국어
      ValueError로 즉시 중단 — openai SDK의 애매한 TypeError 전 제단.
    - 런타임 유의: `stream_usage` 자동 True → 요청에 `stream_options` 포함. 게이트웨이가
      거부하면(400) 생성 인자에 `stream_usage=False` 폴백. `disabled_params` 기본으로
      `parallel_tool_calls` 미전송 — 순차 툴 루프라 무해.

14. **개요 문서: 파일이 곧 SSOT인 fs 네이티브 소스 문서 + 첫 PUT 엔드포인트** (2026-10-02)
    - 개요 문서(`workspaces/<slug>/sources/overview.md`)는 소스 탭에서 웹으로 작성·편집하는
      특수 소스다. 용도가 **인터뷰 기본자료 전용**(plan→derive 결과물 생성 체인 미사용)이므로
      plan처럼 DB SSOT·세대·승인·채번 개념을 두지 않는다 — 파일 자체가 권위다. plan.md는
      DB `Plan.markdown`의 미러(원칙 1)라는 것과 계약적으로 다른 점이다. sources/ 안의
      파일이라 소스 목록·인터뷰 주입 컨텍스트(`read_sources_context`)·프로젝트 삭제
      정리(`delete_project`의 rmtree)가 기존 경로로 자동 동작한다.
    - 계약: `GET/PUT /api/projects/{pid}/overview`(업서트) + `GET /sources/{name}/download`
      (DELETE `{name}`과 대칭). PUT은 코드베이스 첫 사용 — 리소스 경로 고정·전체 본문
      교체·멱등 저장에 맞는 메서드다. 개요 문서만 소스의 덮어쓰기 금지(409) 규칙 예외이며,
      빈 내용 저장은 409 거부("파일이 존재하면 내용이 있다" 불변식 유지).
    - 개행 규약 예외: 기존 `Path.write_text`(newline=None → Windows CRLF 변환) 대신
      `validate_overview_content`가 전수 LF 정규화 + `write_bytes`로 LF 고정 — 이 문서는
      다운로드해 사용자 Git 저장소로 직접 갈 수 있다. 읽기는 `utf-8-sig`(BOM 제거, Notepad
      대응)와 짝을 이룬다. 동시 편집은 last-write-wins(이력 콘셉트 미도입).

15. **잡 진행 표시: 폴링 단일 소유자 + derive_build 도메인 행 후발 생성** (2026-10-02)
    - 배경: 진행 배너(5381af9)가 런타임 DB에 `jobs.progress` 마이그레이션 미적용 상태로
      침묵했다 — `/api/jobs` SELECT가 500이 돼도 프론트가 `jobsQ.isError`를 렌더하지 않아
      화면에 흔적이 없었고, 워커 태스크(`asyncio.create_task`의 첫 `claim_next_job`
      SELECT)도 조용히 죽어 잡이 영구 queued에 머물렀다.
    - 변경 1 (폴링 소유자): `["jobs", pid]` 쿼리의 refetchInterval은 shared/lib
      `useActiveJobs` 하나만 보유한다 (헤더 ActivityPill이 아핀 — 탭 전환에도 폴링 생존).
      TanStack v5는 refetchInterval이 관측점별 타이머라 interval 없는 관측점은 타이머를
      만들지 않는다 — 탭 뷰모델(useOutputs/useReviews)은 소비만 하고 소유자 1곳에만 중복
      요청이 없다. 에러 시 5초 주기 재시도로 자가 복구. 경과 갱신은 structural sharing
      (동일 페이로드 폴링 시 리렌더 없음) 때문에 폴링만으론 안 되므로 `useTickingNow`(1s
      틱, 조건은 `some(running)` — activeJob.status가 아닌 이유: 직렬 워커는 최오부 잡을
      running, latestActive는 최신 queued를 가리킨다)로 지각 시각을 공급한다.
    - 변경 2 (도메인 행 후발 생성): `derive_build`의 Derivative/Build 행 생성을
      `atomic_build` 이후로 밀었다. report_progress가 세션 전체를 즉시 커밋하는 facade
      계약상 커밋 시점에 대기 중 도메인 행이 있으면 빌드 실패 시 고아가 남는다 — 이제 빌드
      루프 내부에서도 fmt별 `report_progress(detail="HTML 작성 중")`가 안전하다 (불변식:
      모든 session.add는 atomic_build 이후). 빌더 실패 → 고아 0행·output 무손상
      (test_build_failure_leaves_no_derivative_or_output로 잠굼).
    - 계약 불변: jobs facade·JobOut·openapi.json/types.gen.ts 미변경 (diff 0 증명).
      진행 상세(detail)는 job.progress JSON 내부 필드일 뿐 스키마는 free-form 유지.

16. **derive 소진 오류의 실제 라벨·진단 고정 + 실패 job 오류 전문 토글** (2026-10-02, `create-readme`)
    - 배경: HTML 파생물 job #34(plan_id 16, llm-wiki) 실패 시 실패 배너가
      `j.error.split("\n")[0]`으로 첫 줄만 보여
      "수치 무결성 위반이 3회 재시도 후에도 해소되지 않았습니다 (…):"에서 끝났다. 진단
      목록(수치 '4' plan 소실·'5'/'6' 창작 추가)은 DB `jobs.error`에 온전히 저장돼 있었다.
      같은 조사에서 `Deriver._run_llm`의 `last_findings`는 red 판정 시에만 채워지므로,
      마지막 시도가 스키마 검증 실패이거나 도구 호출 없이 소진되면 같은 "수치 무결성
      위반" 헤드 + 빈 진단으로 raise되는 잠재 결함이 확인됐다. 프론트 `fmtDateTime`도
      UTC ISO를 `slice`해 현지시각을 허상으로 표기했다(21:54 KST 실패 잡이 "12:54"로
      보여 원인 추적을 혼란시켰다).
    - 변경: (1) `planforge/derive.py` — `_run_llm`의 validate 클로저가 마지막 검증 실패
      종류("numeric"|"schema")·진단 본문·판정 시도 수를 추적하고, 소진 시 `_final_error`
      가 실제 라벨로 raise한다. 수치 소진은 기존 문구를 그대로 유지, 스키마 지속 소진은
      "스키마 검증 실패가 N회…" + builder 스키마 오류문을, 도구 미호출 소진은
      "LLM이 N회 응답 동안 … 도구를 호출하지 않았습니다" + 마지막 텍스트 응답(앞 500자)을
      실는다. 스키마 지속 소진은 `DeriveSchemaError(DeriveError)` 하위형으로
      `isinstance(e, DeriveError)` 계약을 유지한다.
      (2) `jobs/application/worker.py::_classify` — `DeriveSchemaError → SCHEMA`
      (하위형 판정이 `DeriveError → LLM` 앞에 온다).
      (3) `planforge/llm/loops.py` — final 상태의 `tool_call`(마지막 응답이 도구 없이
      끝나면 None)·`resp_content`(마지막 텍스트 응답)를 소진 라벨링 입력으로 docstring에
      명시 — 그래프 상태·노드·엣지 무변경.
      (4) 프론트 — 공용 `shared/components/JobErrorDetail`(요약 행 + "자세히" 토글,
      저장된 오류 전문 pre — Traceback 포함)로 실패 배너·작업 큐 실패 행·plan 반영
      배너를 교체한다. `ERROR_CLASS_LABEL`은 shared/lib/jobs의 `JOB_ERROR_CLASS_LABEL`
      로 공용화. `fmtDateTime`은 UTC → 로컬 변환으로 고정, date-only 2곳
      (ProjectsPage·ProjectPage 생성일)은 신규 `fmtDate`로 같은 분류 결함을 함께 교정.
    - 불변: 재시도 tool 피드백 문구·nudge 문구·메시지 조립 순서(편차 11 불변 항목,
      테스트 `llm.calls[N]` 고정) 1바이트 유지 — 실패 라벨링은 validate 클로저 쪽
      추적으로만 하고 루프 그래프·`chat_fn`/`stream_fn` dict 계약은 불변.
      `JobOut`·`JobErrorClass` enum·openapi 계약 무변경(`npm run gen:types` 불필요,
      SCHEMA 분류값은 이미 frontend 계약에 존재). 본 항목은 편차 11의 "오류 메시지
      불변"을 소진 최종 오류에 한정 개정한다 — 수치 소진 first line은 그대로(기록·
      테스트 호환), 스키마/도구 미호출은 신규 템플릿. 기존 실패 job 행의 저장 문자열은
      백필 없이 verbatim 표시.

17. **수치 무결성 판정의 derive 게이트 폐지 — 검수 단계로 권위 이관** (2026-10-02, `create-readme`)
    - 배경: 수치 위반이 derive의 하드 실패로 처리됐다(job #34 — 소진 3회 → FAILED/LLM
      라벨). 스펙(요청서 §2.1 원칙 3 원문: "검수 단계에서 기계적으로 대조 검증한다" —
      CLAUDE.md 재압축 때 유실)은 반대다: FR-3.2는 파생물 생성의 유일한 중단점을 골격
      검증으로 한정(원칙 8), FR-3.4의 실패 보고 계급은 스키마/스크립트뿐이고 수치 실패
      계급이 없으며, FR-4.1이 수치 무결성 검수를 검수 단계 소관으로 규정한다(수용 기준 3
      "검수가 🔴로 탐지"). legacy(make-doc)도 생성 중 numcheck를 실행하지 않았다. 검수
      핸들러는 이미 **동일 numcheck 엔진**을 Derivative `d.json`에 재적용하므로 권위 이관
      후에도 잠금 기준은 그대로다.
    - 변경 (사용자 결정 확정 2건 반영): (1) derive는 numcheck를 **재시도·중단 게이트로
      쓰지 않는다** — 스키마 통과 payload에 **1회 측정**만 하고 findings를 `DeriveResult`
      · job result에 보고한다(`derive_build`가 `result.findings`에 영속 기록). 수치
      왜곡 주입에도 job은 done이며 위반 수치가 실린 산출물이 채번돼 존재한다. (2) red
      잔여 시 같은 커밋에 검수 잡을 **자동 큐잉**한다(`review` facade
      `enqueue_auto_review` — 같은 plan 세대 활성 검수 있으면 중복 큐잉 차단; 클린
      생성은 자동 검수 없음 — 수동 실행 유지). 자동 잡도 단일 워커 직렬 루프가 처리하며,
      run_review가 동엔진 판정으로 리포트를 닫으면 FR-4.2 🔴 → FR-4.3 plan만 수정 →
      재승인 → 재생성(버전 +1)의 유일 수정 경로로 귀결된다. 잡 진행 불변식(대기 중 도메인
      행 0) 유지 — 큐잉은 모든 report_progress 뒤, run_job의 단일 커밋에 묶인다.
    - 불변: 스키마 재시도 피드백 문구·nudge 1바이트 유지(편차 11 항목 중 numcheck 재시도
      분기만 소멸 — `validate`는 재조립 없이 스키마 분기 하나가 된다). 도달하는 하드
      fail은 **스키마 소진**(`DeriveSchemaError` → SCHEMA 분류)과 **도구 미호출 소진**
      (도구 없는 응답 → LLM 분류)뿐 — 결정 16의 라벨링은 스키마/도구 미호출 케이스로
      한정 보존(수치 소진 라벨링 분기는 도달 불가가 되어 제거, 라벨링 기법 전반·프론트
      토글 유지), 골격 게이트(원칙 8) 유지. `JobOut.result`는 free-form dict라 findings
      키 추가도 계약 무변경(결정 15 선례 — openapi diff 0, `npm run gen:types` 불필요).
    - 프론트: 최신 done derive가 red를 남겼을 때만 산출물 탭에 info 배너
      ("생성 완료 — 수치 무결성 미달 N건(🔴 M건) — 검수가 자동 실행되어 대조합니다",
      검수 탭 이동 버튼·dismiss, 최신 클린 생성이 배너를 대체) + 작업 큐 상세줄에
      `· 위반 N건(🔴 M건)` 접미. CLI `derive`는 측정값을 `주의:`로 출력하고 exit 0 유지
      (게이트는 `python -m planforge numcheck` exit 1 계약으로 별행).
    - 리스크 수용: 잘못된 수치 산출물이 채번돼 존재하는 상태가 생긴다 — 상쇄: red 잔여
      즉시 자동 검수 → 검수 동엔진 재판정(빠짐 없음) → findings 영속 기록 → FR-4.3 재생성
      루프. 채번은 덮어쓰기 없으므로 과거 버전 추적 가능(원칙 5).

18. **인터뷰 턴 계약 강화 — 본문 선택지 나열 탐지 + 프로필 tool_choice 강제** (2026-10-03, `for-gemma4-26b`)
    - 배경: 모델 교체(특히 소형 모델)마다 인터뷰 질문 구조가 흔들린다. (1) 선택지를
      options 배열이 아니라 질문 본문에 서술형 `예:` 줄로 나열하면 options 없이
      allow_free=true만으로 검증을 통과하고, 프론트는 `options.length` 기준으로
      버튼을 렌더하므로 "본문엔 보이고 버튼은 없다"(직접 입력만) 상태가 된다.
      (2) 도구 호출이 흔들리는 모델은 텍스트 전용 출력 → nudge 1회 → TurnError
      (세션 FAILED)로 끝난다. 검토 과정에서 비-object 도구 인자(list/str)가
      AttributeError로 세션 FAILED 되는 보호 구멍도 함께 확인됐다.
    - 변경: (1) `validate_tool_args` — 본문 옵션 유사 줄(`예:`·`예)`·`보기:`·`답:`·
      `1.`·`2)`·`①..⑳`·`가)…차)`·`(1)`·`(가)`(A)·불릿) 2줄 이상이면 계약 위반으로
      거부 — options 유무와 무관(선택지는 options 배열로만 전달하는 계약). 피드백은
      위반 문항 번호·원문 줄 인용·이동안(options 이동 / 나열 제거+allow_free)을 한 번에
      알려 재시도 1회로 수렴시킨다. 인자 비-object는 AttributeError 대신 ToolError
      재시도 피드백으로, JSON 파싱 실패는 한국어 피드백으로. options 라벨은 strip
      정규화·빈 라벨 거부, description은 문자열 검사. (2) provider — `ProfileConfig
      .tool_choice`(기본 auto) → `bind_tools` 전달(하드코딩 "auto" 대체; "required"는
      도구 미호출 모델이 도구만 호출하게 강제). 계약 외 값은 생성 시점 ValueError.
      계약 문서 `docs/INTERVIEW-TURN-CONTRACT.md` 신설(계약 4종 동시 점검 + 모델 교체
      체크리스트 — CLAUDE.md 규칙 절차 참조).
    - 불변: `chat_fn`/`stream_fn` dict 계약·이벤트 포맷·`_to_lc_messages` 위치·
      `max_retries=0`·anthropic 금지·OpenAPI/프론트 무변경(`pending_questions`
      unknown[] 유지, `npm run gen:types` 불필요). ERROR 피드백 재시도 경로
      (`route_after_blocking`)·MAX_TOOL_TURNS·recursion_limit 상수 무변경. 이력에는
      원본(raw) 도구 인자가 남고 정규화는 pending_questions·questions 이벤트에만
      적용 — 기존 검증기와 동일 관행.
    - 리스크 수용: (1) 본문 불릿 나열이 하위 기준 나열인 정상 질문이어도 위반 취급된다
      — 구조 정돈 유도가 목적이며, 오탐 실관측 시 정규식 불릿 arm만 제거한다. (2) 일부
      OpenAI 호환 릴레이는 required를 무시(동작 변화 없음 — auto와 동일)하거나 거부할
      수 있다 — 프로필별 옵트인+기본 auto로 피해를 한정하고 되돌리는 절차를
      config.example.json·계약 문서 체크리스트에 명시.

19. **인터뷰 질문 품질 안정화 2차 — 퓨샷 강제 + 프론트 선택지 렌더 정돈** (2026-10-03, `for-gemma4-26b`)
    - 배경: 결정 18의 서버 검증·재시도·tool_choice 이후에도 모델 교체마다 질문 구조가
      흔들린다는 관찰 — 남은 원인 3곳. (1) `interview.md`에 ask_questions JSON 예시가
      0개 — 형태 강제가 명령형 문장 3중뿐이며, write_plan의 "그대로 모방한다" 완성
      예시 블록·derive 프롬프트의 스키마 예시와 달리 ask_questions만 퓨샷이 빠져
      있었다. (2) 프론트 혼돈 근원 — 객관형 문항에도 직접 입력이 기본 병기되고 옵션
      선택 중 입력값이 제출 시 조용히 폐기되며, 질문 본문 개행이 붕괴되고, 오류가 나도
      답변이 클리어되며, 라운드 목표(round_summary)는 SSE payload에만 존재해 화면
      어디에도 없다. (3) 부수 결함 — 같은 user 메시지가 모델 컨텍스트에 2회 중복 전송
      (`run_turn` 적립 → autoflush로 `_history` 포함 → 재부착)되고, /answers가 DB
      user 행을 이중 적립한다.
    - 변경 1 (퓨샷 + 매턴 리마인더): `interview.md`에 `## ask_questions 인자 형식
      (완성 예시)` 섹션 신설 — 객관형 2문항(options 3개/2개, description 근거) +
      서술형 1문항(allow_free만) 실물 JSON. "둘 다 있는" 문항은 예시에 싣지 않는다
      (소형 모델의 항상 병기 경향 유발 방지). `agent.py`의 `_system_prompt`는 매턴
      시스템 프롬프트 끝(응답 직전 위치)에 `## 이번 턴 ask_questions 리마인더`를
      부착하며 round_summary의 라운드 번호는 `sess.round_no + 1`로 서버가 계산해
      주입 — 모델이 번호를 지어내는 지점을 제거한다 (예시 번호 복사 방지 각주 포함).
    - 변경 2 (round_summary 영속): 세션 행 `pending_round_summary`(nullable Text,
      alembic 9c1f4e7b8a20) 영속 → `SessionOut` 노출 → 이력 questions EVENT payload에도
      summary 포함 — 재접속 리플레이에 라운드 목표 보존. 프론트 답변 카드·정적 이력
      카드 부제 "라운드 N — 목표: …" (구세션 행은 summary 부재 → 폴백 제목).
    - 변경 3 (user 적립 단일 권위): `run_turn`의 선행 적립분만 남기고 재부착 삭제,
      /answers의 선행 적립+커밋 삭제 — 모든 호출자(/kick·/turn·/answers·게이트)는
      선행 적립 없이 message를 넘기고 `_history()` 결과가 이력과 1:1이 된다. 구세션의
      중복 user 이력 행(리플레이 버블 2개)은 백필 없이 방치(사용자 결정).
    - 변경 4 (렌더 정돈): 옵션 클릭↔직접 입력 상호배타(onPick 패치가 반대값을 명시적
      해제) — 제출 계약(AnswerItem 1문항 1값)과 정합하며 "free 조용히 폐기" 암묵
      결함이 시각적 해제로 드러난다. 옵션 버튼은 label·description을 분리 span으로
      쌓는다(.option-label/.option-desc). `.q-text` pre-wrap(개행 보존). `run()`은
      오류(error 이벤트·예외)에서 false 반환 — `turn()`은 오류 없이 끝났을 때만
      답변·초안을 비운다(오류 시 유지 — 재제출 대비).
    - 불변: `tools.py` 스키마·`validate_tool_args`(권위), `chat_fn`/`stream_fn` dict
      계약, EVENT seq·`_history` role 필터(USER/ASSISTANT/TOOL만), AnswerItem 1문항
      1값, 직접 입력 기본 병기(`allow_free ?? true`), openapi 계약은
      `pending_round_summary` 추가 1개(diff 확인) — `npm run gen:types` 동반.
    - 리스크 수용: (1) 완성 예시+리마인더로 턴당 system 토큰 ≈+0.6k — 8턴 세션 기준
      수용(강제 우선, 사용자 결정). (2) 소형 모델이 예시의 "라운드 3"을 그대로 복사할
      수 있음 — 리마인더의 서버 계산 값으로 방어하고, 관찰되면 예시 번호를 자리표화.
      (3) 정적 이력 카드의 옵션 표기(description inline hint)는 인터랙티브 카드와
      압축 표기가 다르다 — 참조 전용이라 의도로 유지. (4) 서술형을 객관형으로 나열
      하는 모델은 여전히 결정 18의 검증 거부→재시도에 의존한다 — 퓨샷 위반 억제가
      1차, 검증이 2차 방어선.

20. **인터뷰 모름 답변 추천 — ask_questions suggestions·(모름) 마킹·(미확정) 팩트 경유** (2026-10-03, `for-gemma4-26b`)
    - 배경: 모름·몰라·미입력 계열 답변의 서버 쪽 처리가 전무했다. free_text는
      strip() 후 LLM에 그대로 전달되고(모름 감지·취급 코드 0건), 미제출(누락) 문항은
      `[라운드 답변]` 조립에서 번호 자체가 생략돼 LLM이 무응답을 추론해야 했다. 추천
      답변 제시 지점 선정에서 두 방식을 모두 채택: (1) 질문 제시 시점 카드에 추천
      후보 칩, (2) 모름 답변 뒤 턴에서 LLM이 근거 있는 추천을 (미확정) 팩트로 적립.
    - 변경: (1) `ask_questions` 스키마에 문항당 선택 필드 `suggestions`(문자열 배열,
      최대 3개, 한 줄 문장) — `validate_tool_args`는 타입·개수·개행(리터럴+이스케이프)·
      120자 길이만 결정론 검증하고 strip 정규화한다. "소스·확립 팩트에서 도출, 추측이면
      (미확정) 유도"는 프롬프트(interview.md 질문 설계 규칙·모름 답변 처리 절) 소관.
      칩 클릭은 자유 입력 채움(선택↔입력 상호배타 유지), 카드 [추천으로 전체 제출]은
      미답변 문항을 suggestions[0]으로 결정론 채움 — 클라이언트 조립이며 서버 계약
      변화 없음. (2) `/answers` 조립은 인덱스 dict 기반 — 미제출 문항에 `→ (모름)`
      고정 마킹 라인을 채우고 인덱스 오름차순 정렬한다(무응답 인덱스 소실 차단,
      사용자 원문 재작성 없음). 빈 answers 배열은 409("전부 모름" 제출 기각 — 전 문항
      모름 오연동 방지, 문항별 모름 입력·추천 칩이 커버). (3) 모름 계열 답변을 받은
      턴의 LLM은 소스·확립 팩트에 근거가 있는 추천 후보를 `save_facts`(content에
      (미확정) 필수, source "인터뷰 추천")로 제시 — fact_gate 승인이 유일한 채택
      승인 지점이고 승인 전 턴은 소모되지 않는다. free_text는 서버 마킹 없이 원문
      전달(정규식 (모름) 덮어쓰기는 부분답변 오표기 + 원칙 3 충돌로 기각).
    - 불변: 새 도구·엔드포인트 없음(save_facts·fact_gate 재사용), AnswerItem·SessionOut·
      FactOrigin(INTERVIEW)·turn_graph 불변, openapi diff 0(`pending_questions`
      unknown[] 유지 — `npm run gen:types` 불필요). save_facts+ask_questions 병행
      금지는 기존 dispatch_blocking 계약 유지(첫 blocking만 실행 — 소실되는 쪽이
      ask_questions라 안전측). 정적 이력 카드(StaticQuestions)는 suggestions 미렌더
      (참조 전용 표기 차이 유지 선례). "모름" 표현 자체는 팩트로 적립하지 않는다.
    - 리스크 수용: (1) 모델의 always-emit suggestions 경향 — 예시는 서술형 1문항에만
      싣고 프롬프트 제한("근거가 없는 항목에는 싣지 않는다")이 담당, 구조 검증은 결정
      18 재시도 경로로 수렴. (2) suggestions는 LLM 추론 도출값 — (미확정) 필수·
      fact_gate 수정 가능이 방어선이며, 확정 전환은 commit_facts(edits) 기존 경로.
      (3) 결정 19 리마인더 토큰에 +1줄(≈+0.05k/턴) — 수용.

21. **인터뷰 제안서 아크 고도화 — 서사 주제 그룹 5종·plan 포맷 배치 가이드** (2026-10-04, `for-gemma4-26b`)
    - 배경: 제안서 아크는 요청서 FR-2.3 원문 수준의 한 줄("문제 / 해결책 / 기대효과")로
      남아 있었다 — 개발설계서 설계 결정 설문(주제 그룹 5개 + 옵션 카드 예시)과 달리
      서사·근거·리스크·요청 사항이 인터뷰에서 뽑히지 않아 plan.md 목차가 얇아진다.
      plan 생성 지시는 interview.md write_plan 포맷 섹션이 유일(plan_revise는 검수 반영
      전용, derive는 1:1 변환) — 인터뷰→plan 연결 보장의 유일한 수정 지점이기도 하다.
    - 변경: (1) interview.md 제안서 아크를 주제 그룹 5종(현황·문제 정의 / 영향·기회 /
      제안 해결책·차별성 / 기대효과·실증 근거 / 리스크·대응·요청 사항) + 예시 질문
      옵션 카드로 심층화 — 각 주제는 주장 + 근거(로그 항목 또는 `(미확정)`)를 주제당
      1개 팩트로 적립한다 (개발설계서 "결정+이유+대안" 패턴의 제안서 버전). 근거 없는
      사례 창작을 막기 위해 실증사례를 독립 그룹으로 두지 않고 기대효과 수치의 근거로
      흡수. (2) [제안서] 종료 체크리스트 1→5항. (3) 핵심 메시지 3개를 아크 세 축
      (문제·영향 / 해결책·차별성 / 기대효과·요청)과 1:1 대응시키고, 아크 라운드에서
      메시지가 흔들리면 `confirm_key_messages` 재제시·재승인 — 게이트 재오픈은 기존
      기계 동작(agent.py `_confirm_key_messages`). (4) plan.md 포맷에 제안서 구성
      가이드 신설 — 아크 순서→슬라이드 유형 배치(2단=현황·문제·영향, 표=해결책·차별성·
      리스크, 차트=기대효과, 마무리=요청·확인 계획)와 아크 장 라벨 목차 (개발설계서
      구성 가이드와 대칭). (5) 대칭 e2e
      `test_interview_proposal_arc_full_flow_to_plan_approval` + fewshot 잠금 assert 4개.
    - 불변: 도구 스키마·`validate_tool_args`·area 3종(공통|제안서|개발설계서) — 스키마
      무변경(openapi diff 0 확인, `npm run gen:types` 불필요). agent.py·turn_graph·
      parser·filter·plan_revise·derive 프롬프트·프론트 무변경. MAX_ROUNDS=8·골격
      검증·confirm_key_messages "라운드 2 종료" 시점(tools.py:119 하드코딩) 유지.
      ask_questions 완성 예시(퓨샷)와 plan 완성 예시 블록 무변경 — 표기법 시연 소관 분리.
    - 리스크 수용: (1) 프롬프트 길이 +~45행(매턴 전체 주입) — 개발설계서 블록과 대칭
      규모, 옵션 카드를 그룹당 주로 2개로 제한해 수용. (2) 예시 카드 라벨의 원문 카피
      위험 — 개발설계서 선례와 동일 수준, "실제 사례 기반" 규칙 + 실세션 관찰이 방어선.
      (3) 아크 슬라이드 순서는 서버가 결정론 검증하지 않는다(골격만 검증 — 검증 추가는
      parser/agent 수정이 필요해 의도 제외) — 프롬프트 규칙 + 검수(review) 단계가
      후속 방어선.

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

`python scripts/export_openapi.py`(backend/에서)로 export한 결과가 커밋 계약이다.
(2026-10-03 실측 갱신 — **venv python이 현재 커밋 계약 렌더링과 일치한다:**
venv fastapi 0.141.1+pydantic 2.13.5는 `UploadFile`을 `contentMediaType: application/octet-stream`으로,
ValidationError에 `input`/`ctx`를 렌더링한다. 시스템 python(fastapi 0.115.11+pydantic 2.12.3)은
`format: binary`·input/ctx 제거 렌더링이라 export하면 계약 diff가 유발된다 — 문서 초작성 당시와
환경이 반전됐다. 세션마다 export 전 2환경 중 커밋 계약과 일치하는 쪽을 `git diff`로 확인할 것.)
export 환경을 의도적으로 업그레이드했다면 별도 커밋에서 계약을 재생성·커밋할 것(프론트 `npm run gen:types` 동반).