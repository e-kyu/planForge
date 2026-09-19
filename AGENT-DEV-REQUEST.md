# 개발 요청서 — 기획 문서 생성 Agent 웹 서비스 ("report-agent")

> **이 문서의 용도**: Claude Code에 개발을 위임하기 위한 요청서다. 새 세션에서
> "AGENT-DEV-REQUEST.md를 읽고 개발을 시작해줘"로 전달하는 것을 전제로 작성했다.
> 요청서만으로 개발이 가능하도록 현행 시스템 분석 → 목표 사양 → 마일스톤 → 수용 기준까지 담는다.

---

## 1. 배경 및 목적

현재 저장소(`makeReportAgent2`)는 **Claude Code 위에서 동작하는 기획 문서 생성 Agent**다.
인터뷰 → 기획서(plan.md) → 파생물(slides.json·report.json) → 빌더 스크립트 →
산출물(PPTX·MD·HTML·DOCX) → 검수의 워크플로를 Claude Code의 커맨드(`/plan-doc`,
`/make-ppt`, `/make-doc`, `/review-doc`)와 스킬(`ppt-design`)로 구현해 두었다.

이 시스템을 분석해 **동일 도메인(제안서·개발설계서 생성)을 그대로 이식한 웹 서비스**를
새로 개발한다. 비개발자도 브라우저에서 인터뷰에 답하고, 기획서를 승인하고, 최종 문서를
내려받을 수 있어야 한다. Claude Code 실행 환경에 대한 의존은 모두 제거한다.

### 목표 한 줄

> "인터뷰에 답하면 제안서·개발설계서가 PPT·문서로 나온다"를 브라우저에서, Claude Code 없이.

---

## 2. 현행 시스템 분석 (이식 대상의 근거 자료)

새 시스템을 설계하기 전에 반드시 아래 파일을 읽고 이식 범위를 확정할 것.
이 절은 요약이며, 원문이 우선한다.

| 현행 자산 | 역할 | 이식 방향 |
|---|---|---|
| `CLAUDE.md` | 전체 규칙 (워크플로·plan.md 포맷·report.json 스키마·버전 규칙) | 시스템 프롬프트/정책 문서의 원전 |
| `.claude/commands/plan-doc.md` | 인터뷰 에이전트 절차 (가설 선제시·가변 라운드·팩트 적립) | 인터뷰 에이전트의 행동 명세 |
| `.claude/commands/make-ppt.md` | plan.md → slides.json 변환 + 빌드 절차 | 파생물 생성 에이전트 명세 |
| `.claude/commands/make-doc.md` | plan.md → report.json 변환(문서체 재구성) 절차 | 파생물 생성 에이전트 명세 |
| `.claude/commands/review-doc.md` | 검수 체크리스트 (구조·태그·수치 무결성·세대 대응) | 검수 에이전트 명세 |
| `.claude/skills/ppt-design/SKILL.md` + `layouts.md` | 슬라이드 7종·색·폰트·좌표 + slides.json 스키마 | 디자인 토큰·레이아웃 정의 (그대로 재사용) |
| `scripts/build_ppt.py` | slides.json → PPTX 조립 (결정론) | **원형 유지, 빌드 서비스로 재사용** |
| `scripts/build_doc.py` | report.json → md/html/docx 조립 (결정론) | **원형 유지, 빌드 서비스로 재사용** |
| `scripts/theme.py` | 색/폰트/여백 토큰 (스킬과 동일 값 유지) | 그대로 재사용 |
| `samples/*.sample.json` 외 | 스키마 계약 예시·스모크 테스트 입력 | 계약 테스트 fixture로 이식 |
| `projects/<P>/docs/interview-log.md` | 세션을 넘어 유지되는 확정 팩트 저장소 | DB 팩트 테이블로 승격 |

### 2.1 이식해야 할 핵심 설계 원칙 (기술 독립 원칙 — 가장 중요)

1. **SSOT(Single Source of Truth)**: 콘텐츠의 유일한 원본은 plan.md 하나다.
   파생물(slides.json·report.json·산출물)은 절대 직접 수정하지 않고 항상 원본에서
   재생성한다. 수정 요청은 반드시 plan.md 반영 → 파생물 재생성 순서로 처리한다.
2. **LLM과 코드의 역할 분리**: LLM은 "콘텐츠 변환"만 한다(plan.md 해석, 문서체 재구성,
   스키마 매핑). 파일 조립·좌표 배치·채번 같은 결정론적 작업은 Python 빌더가 담당한다.
   LLM이 pptx/docx 바이너리를 직접 만들지 않는다 — 이것이 품질 재현성의 핵심이다.
3. **수치 무결성**: 수치·표·차트 데이터·`(미확정)` 표기·근거/출처 문자열은 plan.md와
   **한 글자도 다르게 복사되지 않는다**. 재구성(개조식→서술형)은 문장에만 적용하고,
   plan에 없는 내용을 창작하지 않는다. 검수 단계에서 기계적으로 대조 검증한다.
4. **팩트 선(先)적립**: 인터뷰에서 확정된 수치·약속은 먼저 팩트 저장소
   (interview-log)에 기록한 뒤 plan.md에 반영한다. 추측 수치는 `(미확정)`으로 명시한다.
5. **버전 채번 규칙**: 산출물명은 `<문서 제목>_vNN.<확장자>`. 같은 프로젝트·같은
   확장자 내 최대 vNN+1이며 확장자별로 독립 시퀀스다. 절대 덮어쓰지 않는다.
6. **다중 문서 태그**: 하나의 plan.md에서 제안서·개발설계서가 공존할 수 있다.
   슬라이드에 `[문서: 제안서+개발설계서]` 태그를 붙여 문서별로 필터링하며,
   각 문서의 목차는 해당 문서 슬라이드만 01..NN으로 재채번한다.
7. **디자인 토큰 단일화**: 색·폰트·여백은 `theme.py` 토큰 하나가 권위이며, 스킬 문서와
   값이 동일하게 유지된다. 디자인 변경은 문서(SKILL.md)·토큰(theme.py)·렌더러(빌더)·
   샘플을 **4종 세트로 동시 수정**한다(과거 누락 사고 있음).
8. **골격 검증**: 파생물 생성 전 표지·목차·마무리·내용 슬라이드가 최소 1개씩 있는지
   검증하고, 미달이면 생성을 중단한다.

### 2.2 Claude Code 종속 요소 (웹 서비스에서 교체 대상)

| 현행 | 종속 내용 | 웹 서비스 대체물 |
|---|---|---|
| AskUserQuestion 도구 | 최대 4개 선택지 인터뷰 UI | 채팅 + 선택지 카드 컴포넌트 |
| Skill 로딩 | 필요 시점에 ppt-design 로드 | 에이전트 단계별 시스템 프롬프트에 상시 포함 (문서량이 작아 상시 포함이 단순) |
| 커맨드 파일 (`/xxx`) | 사용자가 슬래시로 단계 진입 | UI 버튼·상태 머신으로 자동 진행 |
| 파일시스템 (projects/<P>/...) | 상태 영속화 | DB + 프로젝트별 워크스페이스(파일 트리 유지 권장) |
| 슬래시 인자 프로젝트 결정 | `projects/*/plan.md` 나열·사용자 선택 | 프로젝트 목록 화면 |

---

## 3. 목표 시스템 아키텍처 (웹 서비스)

```
[브라우저]
  프로젝트 목록 / 인터뷰 채팅(선택지 카드) / plan.md 뷰어·편집·승인
  산출물 갤러리(버전별) / 다운로드 / 검수 리포트
        │ REST(또는 WebSocket — 인터뷰 스트리밍)
[웹 백엔드]
  세션 관리 · 프로젝트/버전/팩트 DB · 파일 워크스페이스 · 인증
        │
[에이전트 오케스트레이터]  ← LLM: provider 추상화 계층 (ollama/openai —
  OpenAI 호환 프로토콜로 통일, tool calling + SSE 스트리밍)
  단계 상태머신: interview → plan → derive(slides/report) → build → review
  단계별 시스템 프롬프트 = 현행 커맨드 md 이식본
  도구: save_facts / write_plan / write_slides_json / write_report_json /
        run_builder / list_outputs / diff_plan / report_findings
        │ subprocess (Python)
[빌드 서비스] = 현행 build_ppt.py · build_doc.py · theme.py (원형 유지)
  입력: 워크스페이스의 slides.json / report.json
  출력: <project>/output/<title>_vNN.{pptx,md,html,docx}
```

### 3.1 기술 스택 (확정 — 2026-09-17 인터뷰로 결정)

**운영 환경**

- **배포**: 사내 서버 + Docker Compose (backend / frontend / ollama 컨테이너). DB는 호스트
  볼륨의 SQLite 파일. 클라우드는 사용하지 않는다.
- **동시 사용자**: 팀 단위 1~10명. 빌드 동시성이 거의 없어 직렬화·큐 인프라는 경량으로 충분.
- **인증**: 생략 (사내망 신뢰 전제). 사용자 식별은 사용자명 선택 수준. 프로젝트별 접근 제어(§5)는
  데이터 모델에 user 필드 여지만 UI·로그인은 구현하지 않는다 — 추후 확장 항목.
- **파일 저장**: 파일시스템 + Docker 볼륨. **워크스페이스는 현행 디렉토리 규약을 유지**
  (`projects/<slug>/{work,output,docs,assets}`) — 빌더 재사용과 디버깅이 쉬워진다.

**백엔드**

- **언어/프레임워크**: Python + FastAPI. 의존성 관리는 requirements.txt + pip.
- **DB**: SQLite 단일 방언 (프로젝트·세션·팩트·산출물 메타). 파일 하나로 백업·이관이 끝난다.
  팀 단위 1~10명·단일 uvicorn 프로세스·단일 워커 직렬화 전제에 충분하며 (2026-09-19 전환 결정),
  dev·테스트·배포가 동일한 방언을 쓴다. WAL + busy_timeout으로 동시 읽기·쓰기를 처리한다.
- **ORM/마이그레이션**: SQLAlchemy 2.x + Alembic.
- **빌드 작업 처리**: DB 기반 작업 큐 — job 테이블 + 단일 백그라운드 워커 직렬화.
  원칙 5(무손실 채번)의 동시성 요구를 DB 트랜잭션으로 보장하고, job 상태 조회 화면도
  같은 테이블에서 제공한다. Redis·Celery는 도입하지 않는다.

**에이전트 루프 (LLM)**

- **provider 추상화 계층을 직접 구현** — OpenAI 호환 단일 프로토콜
  (`openai` SDK, tool calling + SSE 스트리밍)로 ollama·openai 두 프로바이더를
  base_url/키 차이만으로 소화한다. anthropic SDK·Claude Agent SDK는 사용하지 않는다.
- **지원 프로바이더**: ollama (기본) + openai. Anthropic(Claude)은 초기 미지원 —
  인터페이스는 프로바이더 추가 가능하게 설계해 둔다.
- **모델 지정**: 설정 파일(또는 환경변수)에서 프로바이더별 모델 ID를 지정하며
  기본값은 미지정 — 서버 운영자가 배포 시점에 확정한다. Ollama 모델은
  **tool calling(함수 호출) 지원이 필수**다 (파생물 생성·도구 호출에 필요).
- **단계별 프로필**: interview / derive / review 각 단계마다 다른 프로바이더·모델 조합을
  설정 파일로 지정할 수 있다 (예: 인터뷰는 로컬 Ollama, 수치 무결성이 중요한 변환·검수는
  클라우드 모델).
- **키 관리**: openai 프로바이더의 API 키는 서버 환경변수로만 관리(브라우저 노출 금지).
  Ollama는 사내 서버 내부 통신이므로 키가 없다.

**프론트엔드**

- **프레임워크**: React + TypeScript (Vite).
- **스타일링**: 자체 CSS — `theme.py` 디자인 토큰을 CSS 변수로 연동해 PPT·문서 산출물과
  톤을 맞춘다. 컴포넌트 라이브러리(MUI 등)는 도입하지 않는다.
- **plan.md 편집 UX**: CodeMirror 6 기반 마크다운 에디터 + 미리보기·diff 표시.
  (WYSIWYG는 블록 표기법이 깨질 위험이 있어 채택하지 않음)
- **실시간 통신**: SSE + REST 조합 — LLM 토큰·단계 진행은 SSE 푸시, 사용자 답변
  (선택지 카드 클릭·승인 버튼 등)은 REST POST. WebSocket은 도입하지 않는다.
- **API 계약 타입**: FastAPI가 자동 생성하는 OpenAPI 스키마 → openapi-typescript로
  프론트 TS 타입을 자동 생성해 백엔드↔프론트 계약을 코드로 잠근다.

**저장소 구조**

- 단일 저장소 — `backend/`(FastAPI) · `frontend/`(React) · `workspaces/`(프로젝트
  워크스페이스) 분리. 현행 `scripts/` 빌더·theme.py는 backend에서 import해 재사용한다.

**컨테이너 주의사항**

- 현행 빌더는 Windows 환경(UTF-8, 맑은 고딕)을 전제한다. Linux 컨테이너에서는
  UTF-8 로케일을 명시하고, 폰트는 산출물에 메타데이터로만 기록되므로 서버측 렌더링
  미리보기를 추가하지 않는 한 폰트 설치는 불필요하다. `_sanitize_title` 파일명
  금지 문자 정규화 규칙은 유지한다.

### 3.2 데이터 모델 (초안)

- `Project(id, name_slug, title, created_at, status)`
- `DocumentKind(id, project_id, name)` — "제안서", "개발설계서" … (plan 메타 `산출 문서`)
- `InterviewSession(id, project_id, phase, transcript, pending_questions)`
- `Fact(id, project_id, date, content, source, status[active|archived])` ← interview-log 이식
- `Plan(id, project_id, version, markdown, approved_at)` ← plan.md 세대 관리
- `Derivative(id, plan_id, kind[slides|report], json)` ← plan 세대에 묶인 파생물
- `Build(id, project_id, doc_kind, ext, version_no, file_path, plan_id, built_at)` ← 채번 이식

---

## 4. 기능 요구사항

### FR-1 프로젝트 관리
- FR-1.1 프로젝트 생성(ASCII 소문자-하이픈 슬러그), 목록, 선택.
- FR-1.2 프로젝트별 워크스페이스 자동 생성(work/output/docs/assets).

### FR-2 인터뷰 에이전트 (`/plan-doc` 이식 — 명세 원전: `.claude/commands/plan-doc.md`)
- FR-2.1 **소스 확인**: 인터뷰 전에 글로벌 `sources/` + 프로젝트 `sources/` + 기존 팩트를 읽는다.
- FR-2.2 **가설 선제시**: 질문 전에 소스·팩트로 도출한 예상 뼈대 초안(산출 문서 목록/목적/
  청중/분량/핵심 메시지 후보/예상 구성)을 먼저 제시한다. 맞는 항목은 질문 없이 확정 전환,
  틀린 항목만 정밀 질문 대상. 소스가 텅 비면 초안 없이 뼈대 질문부터 시작한다(임의 추측 금지).
- FR-2.3 **가변 라운드 인터뷰**: 한 라운드 최대 4문항. 아크는 산출 문서별로 다르다 —
  제안서(문제/해결책/기대효과), 개발설계서(요구사항→구성·인터페이스→데이터·모듈→일정·리스크).
  둘 다면 두 아크를 모두 진행하되 공유 팩트는 중복 적립하지 않는다.
- FR-2.4 **라운드별 팩트 확인**: 각 라운드 종료 시 확정 팩트 3~5줄 요약을 보여주고
  사용자 확인 후에만 적립한다. 확인 전에 다음 라운드로 넘어가지 않는다.
- FR-2.5 **모순 처리**: 이전 답변과 충돌하면 즉시 확인한다. 조용히 최신값으로 덮지 않는다.
- FR-2.6 **핵심 메시지 3개**: 라운드 2 종료 시점에 후보를 제시해 승인받고, 이후 라운드의
  목표는 "이 3개를 성립시킬 근거 수집"이다.
- FR-2.7 **종료 판정**: 산출 문서별 체크리스트(공통 + 제안서/개발설계서 아크) 충족 시 종료,
  미달 항목만 추가 질문. 소스가 풍부하면 1~2라운드로 끝나는 것이 정상이다.
- FR-2.8 **plan.md 생성**: 메타(산출 문서·목적·청중·분량) + 핵심 메시지 3개 + 슬라이드
  목록(유형 표기 7종 + 문서 태그 + 근거/출처)으로 작성. 근거 없는 수치는 `(미확정)`.
- FR-2.9 **승인 게이트**: plan.md 전문을 보여주고 사용자 승인 전에 파생 단계로 넘어가지 않는다.

### FR-3 파생물 생성 (`/make-ppt`·`/make-doc` 이식 — 명세 원전: 해당 커맨드 md)
- FR-3.1 대상 문서 선택(산출 문서 2개 이상 시 1회 실행 = 1문서 — 채번 접두어 분리).
- FR-3.2 태그 필터 + 골격 검증(표지·목차·마무리·내용 각 1개 이상) → 미달 시 중단.
- FR-3.3 `plan.md → work/slides.json` (PPT 스키마) / `plan.md → work/report.json`
  (문서체 재구성, 수치 무결성 원칙 3 준수) — **LLM 변환, 사람/검수가 확인**.
- FR-3.4 빌더 실행 → `output/<title>_vNN.<ext>` (원칙 5 채번). 실패 시 오류를 스키마
  문제/스크립트 문제로 분류해 보고.
- FR-3.5 완료 보고: 파일 경로, 슬라이드/섹션 수, 버전 번호.

### FR-4 검수 에이전트 (`/review-doc` 이식 — 명세 원전: 해당 커맨드 md)
- FR-4.1 구조 검수(파생물↔plan), 문서 태그 검수, **수치 무결성 검수**(숫자 추출 대조),
  내용 검수(plan↔팩트), 세대 대응성(같은 plan 세대인지 접두어+내용 대조) 판정.
- FR-4.2 발견사항을 심각도 순으로 보고: 🔴 사실 오류·수치 불일치 / 🟡 표현·구조 / ⚪ 선택.
- FR-4.3 수정 승인 시 **plan.md만 수정** → 파생물 재생성 → 빌드 재실행(버전 +1).
- FR-4.4 검수 중 새로 확정된 사실은 팩트 저장소에 추가.

### FR-5 UI 필수 화면
- 프로젝트 목록 · 인터뷰 채팅(선택지 카드, 팩트 확인 다이얼로그) · plan.md 뷰어/에디터
  (승인 버튼, diff 표시) · 산출물 갤러리(확장자별 버전, 미리보기: md/html은 인라인,
  pptx/docx는 다운로드) · 검수 리포트 화면.

### FR-6 관리/운영
- FR-6.1 팩트 압축(`/compact-log` 이식): 활성 팩트 통합 + 이전 항목 아카이브 이동.
- FR-6.2 디자인 토큰·레이아웃 관리: theme 토큰 변경 시 문서·토큰·렌더러·샘플 4종 세트
  일관성을 점검하는 체크(수동 절차 문서화로 충분).

---

## 5. 비기능 요구사항

- **결정론성**: 같은 slides.json/report.json 입력 → 동일한 빌드 결과. 빌더 코드에는
  LLM을 개입시키지 않는다.
- **원자성**: 빌드 실패 시 output에 불완전 파일을 남기지 않는다(임시 디렉토리 → 이동).
- **무손실 채번**: 어떤 경우에도 기존 산출물을 덮어쓰지 않는다(동시성 포함 — 빌드 직렬화).
- **한글/Windows 호환**: UTF-8, 맑은 고딕, 파일명 금지 문자 정규화(현행 `_sanitize_title` 참조).
- **보안**: LLM API 키(OpenAI) 서버 전용 — Ollama는 사내 서버 내부 통신. 인증은 생략하되
  사용자 콘텐츠는 프로젝트별 소유자 필드를 유지해 추후 접근 제어 확장을 가능하게 한다.
  업로드 파일 검증.
- **추적성**: 모든 산출물이 자신의 plan 세대(plan_id)를 역참조할 수 있어야 한다.
- **테스트**: 현행 `samples/*.sample.json`을 계약 테스트 fixture로 이식해
  빌더 회귀를 잠근다. 수치 무결성 검사(FR-4.1)는 단위 테스트로도 상시 실행.

---

## 6. 마일스톤

| 단계 | 범위 | 완료 판정 |
|---|---|---|
| **M1 코어 엔진** | plan.md 파서·LLM 변환(slides/report.json)·빌더 연동을 **CLI로** 구현 | 샘플 plan → pptx/md/html/docx 생성 성공 |
| **M2 백엔드** | 프로젝트/세션/팩트/채번 API + 에이전트 상태머신 | API로 인터뷰→빌드 e2e 성공 |
| **M3 프론트엔드** | 인터뷰 채팅·plan 승인·산출물 갤러리 | 브라우저에서 e2e 성공 |
| **M4 검수·운영** | 검수 에이전트·세대 대응·압축·배포 | 검수 루프 수용 기준 통과 |

M1을 반드시 먼저 끝낸다 — 빌더 재사용과 LLM 변환 품질(수치 무결성)이 전체 리스크의 대부분이다.

---

## 7. 수용 기준 (최종 인수 테스트 시나리오)

1. **신규 e2e**: 빈 프로젝트 생성 → 인터뷰(가설 선제시 확인 → 1~3라운드 → 팩트 확인 게이트
   동작) → plan.md 승인 → PPTX v01 + MD/HTML/DOCX v01 생성.
2. **수정 루프**: 내용 수정 요청 → plan.md가 수정되고 → 파생물 재생성 → v02 채번.
   slides.json/report.json/output을 직접 고치는 경로가 **없음**을 코드 리뷰로 확인.
3. **수치 무결성**: 의도적으로 LLM 변환에 수치 왜곡을 주입하면 검수 에이전트가 🔴로 탐지한다.
4. **다중 문서**: 산출 문서 2개(제안서+개발설계서) plan에서 문서별로 각각 생성되고,
   각 문서의 목차 번호가 01..NN으로 재채번된다.
5. **채번 독립성**: 같은 프로젝트에서 pptx v02와 md v01이 공존해도 정상 (확장자별 시퀀스).
6. **계약 테스트**: `samples/*.sample.json` 4종이 모두 빌드 성공(현행 스모크 테스트 이식).
7. **무덮어쓰기**: 동일 입력으로 재빌드하면 vNN+1이 생성되고 기존 파일 불변.

---

## 8. 개발 세션에 전달할 참조 파일 (이 저장소 내)

개발 시작 시 아래를 읽게 한다. 원문이 이 요청서의 요약보다 권위 있다.

```
CLAUDE.md                              # 전체 규칙·스키마의 원전
.claude/commands/plan-doc.md           # 인터뷰 에이전트 행동 명세
.claude/commands/make-ppt.md           # PPT 파생 절차
.claude/commands/make-doc.md           # 문서 파생 절차 (md/html/docx 공통)
.claude/commands/review-doc.md         # 검수 체크리스트
.claude/commands/compact-log.md        # 팩트 압축 절차
.claude/skills/ppt-design/SKILL.md     # 슬라이드 7종·색·폰트 + slides.json 스키마
.claude/skills/ppt-design/layouts.md   # 유형별 좌표 상세
scripts/build_ppt.py                   # PPTX 빌더 (재사용 원형)
scripts/build_doc.py                   # 문서 빌더 (재사용 원형)
scripts/theme.py                       # 디자인 토큰
samples/slides.sample.json             # slides.json 계약 예시
samples/report.sample.json             # report.json 계약 예시
samples/plan.sample.md                 # plan.md 포맷 참조점
samples/interview-log.sample.md        # 팩트 로그 형식
```

## 9. 개발 세션 시작 방법

새 Claude Code 세션에서:

```
AGENT-DEV-REQUEST.md를 읽고 웹 서비스 Agent 개발을 시작해줘.
§2.1의 설계 원칙 8개가 계약이며, §6 마일스톤 순서(M1 먼저)를 따른다.
먼저 §8 참조 파일을 읽고 구현 계획을 제시한 뒤 진행해줘.
```