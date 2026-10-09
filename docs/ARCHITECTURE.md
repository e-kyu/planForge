# 아키텍처

가이드(`sources/default_architecture_guidelines.md`) 적용 — 백엔드 모듈러 모놀리식(§1),
프론트엔드 feature-MVVM(§2). 결정·편차의 상세 기록은 `docs/ADR.md` 참조.

## 디렉토리 구조

```
backend/
  app/                        웹 백엔드 (FastAPI)
    api.py                    라우터 집계
    modules/                  도메인 모듈 8종 (projects·sources·plans·derivatives·jobs·
                              facts·interview·review)
      └ <모듈>/               facade.py · presentation/(api·schemas) · application/
                              (유스케이스·에이전트·prompts) · infrastructure/(models)
    shared/                   모듈 간 공용 — config·db·errors·workspace·llm(LLMRegistry)·types
    agents/tools.py           인터뷰 도구 OpenAI function 스키마 + 서버측 검증
  planforge/                  M1 결정론 파이프라인 패키지 (웹 비의존, app→planforge 단방향)
    plan/                     plan.md 파서·문서 필터·골격 검증
    builders/                 build_ppt.py · build_doc.py · theme.py (계약 테스트로 고정 — 로직 변경 금지)
    llm/                      OpenAI 호환 provider(langchain-openai ChatOpenAI) +
                              공용 tool-loop 그래프(loops.py — derive·plan_revise·review·compact)
    derive.py · review.py · numcheck.py
  alembic/                    DB 마이그레이션
frontend/                     React 19 + TypeScript (Vite) — feature-MVVM
  src/features/               화면별 feature 7종 (projects·project·sources·interview·
                              plan·outputs·review) — 각 models/·viewmodels/·views/
  src/shared/                 components/(CodeMirror·마크다운 미리보기) · lib/ · styles/tokens.css
workspaces/                   프로젝트별 워크스페이스 (gitignored — 산출물이 쌓인다)
sources/ · data/              글로벌 소스 · SQLite DB (gitignored)
phases/                       하네스 task/step 계획·상태 (index.json·stepN.md 커밋 대상)
```

## 패턴

- **모듈 경계**: 타 모듈의 테이블·내부 파일 직접 import 금지 — 반드시 대상 모듈의
  `facade.py` 공개 함수 또는 `shared/` 경유. 새 모듈/기능은 기존 것을 템플릿으로 복제.
- **LLM/코드 역할 분리**: LLM은 콘텐츠 변환만. 파일 조립·좌표 배치·채번은 Python 빌더
  (결정론)가 담당한다. 빌더는 legacy scripts의 바이트 동일 이식본으로 로직 변경 금지.
- **작업 큐**: `jobs` 테이블 + 단일 워커(앱 lifespan asyncio 1개, run_job 단일 스레드 직렬).
  병렬 실행 금지 — 빌더 스레드 안전하지 않음.
- **LLM 계층**: `app/shared/llm.py LLMRegistry`가 프로필(interview/derive/review/plan_revise)
  별 provider·모델을 `PLANFORGE_CONFIG`에서 읽는다. provider는 langchain-openai ChatOpenAI
  기반 OpenAI 호환 단일 프로토콜(편차 10), 도구 루프는 langgraph StateGraph(편차 11).
  테스트 주입은 `create_app(llm_overrides=...)` / `JobContext(llm_overrides=...)`.

## 데이터 흐름

```
Project → InterviewSession → Fact → Plan(세대) → Derivative → Build → ReviewReport
```

- 모든 산출물은 자신의 plan 세대를 역참조한다 (추적성).
- 파생 경로: `Plan.markdown`(SSOT) → 미러(`write_plan_mirror`) →
  `planforge/derive.py` → 원자적 빌드(`atomic_build`) → 채번 등록(Build 행) —
  산출물명 `<문서 제목>_vNN.<ext>`, 확장자별 독립 시퀀스, 절대 덮어쓰기 금지.
- 수정은 plan revise → 새 세대 DRAFT → 재승인 → 재생성(버전 +1)만 유일한 경로.

## 상태 관리

- 서버 상태는 **TanStack Query** — GET `useQuery`, 갱신 `useMutation`+무효화.
  View에서 fetch·서버 데이터 로직 금지 — viewmodel 훅 경유(가이드 §4.3).
- 인터뷰 턴은 POST→SSE 계약 — 스트림 소비는 `useInterview` 훅이 직접 관리하고
  종료 후 세션·이력·팩트 쿼리를 무효화한다(**이력이 권위**, 스트림은 표시 보조).
- 비동기 작업(derive·review 등)은 202 수락 → job 폴링.