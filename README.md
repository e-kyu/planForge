# PlanForge — 인터뷰에 답하면 제안서·개발설계서가 PPT·문서로 나온다

브라우저에서 에이전트와 **인터뷰**를 진행하면 확정 팩트가 쌓이고, 그 내용으로
**기획서(plan)** 가 만들어지며, 승인 한 번으로 **PPTX·MD·HTML·DOCX 산출물**이
결정론 빌더에 의해 채번 생성되는 기획 문서 생성 웹 서비스다.

```
[브라우저]  프로젝트 목록 · 인터뷰 채팅(선택지 카드) · plan 뷰어/에디터 · 산출물 갤러리 · 검수 리포트
     │ REST + SSE
[백엔드]    FastAPI · SQLite · 단일 워커(작업 큐) · LLM provider 추상화(OpenAI 호환)
     │
[빌더]      Python 결정론 빌더 — slides.json/report.json → PPTX·MD·HTML·DOCX (채번·원자적 빌드)
```

**핵심 설계**: LLM은 콘텐츠 변환만 담당하고, 파일 조립·좌표 배치·채번은 Python 빌더가
담당한다. 콘텐츠의 유일한 원본(SSOT)은 plan이며, 산출물은 항상 plan에서 재생성되고
**절대 덮어쓰지 않는다**(`<문서 제목>_vNN.<확장자>`, 확장자별 독립 시퀀스).

---

## 1. 전체 워크플로우 (사용자가 경험하는 흐름)

```
① 프로젝트 생성 ──► ② 소스 등록 ──► ③ 인터뷰 ──► ④ plan 작성·승인 ──► ⑤ 파생물 생성(빌드) ──► ⑥ 검수
     (FR-1)          (FR-2.1)      (FR-2)        (FR-2.8~9)         (FR-3)              (FR-4)
                                                                          │
                                              내용 수정 시 ◄── plan 수정 → 재승인 → 재생성 (vNN+1)
```

| 단계 | 무엇을 하는가 |
|---|---|
| ① 프로젝트 생성 | 제목·슬러그로 프로젝트를 만든다. 워크스페이스(`work/output/docs/assets`)가 자동 생성된다. |
| ② 소스 등록 | 기존 기획자료(.md .txt .json .csv, 2MB 이하, UTF-8)를 업로드한다. 인터뷰가 이 자료를 읽고 시작한다. |
| ③ 인터뷰 | 에이전트가 소스·기존 팩트로 **예상 뼈대(가설)를 먼저 제시**하고, 틀린 부분만 질문한다. 라운드당 최대 4문항, 라운드 종료마다 **팩트 확인 게이트**(확인 후에만 적립), 핵심 메시지 3개 승인을 거친다. |
| ④ plan 승인 | 인터뷰 결과로 plan(마크다운)이 생성된다. 편집·diff 확인 후 **승인해야만** 다음 단계로 넘어간다. |
| ⑤ 파생물 생성 | 대상 문서(제안서/개발설계서 등)를 골라 생성 버튼을 누르면 LLM이 plan→slides.json/report.json으로 변환하고, 결정론 빌더가 `output/<문서 제목>_v01.pptx` 등을 채번 생성한다. |
| ⑥ 검수 | 결정론 검수(수치 무결성·문서 태그·구조·세대 대응) + LLM 내용 검수가 🔴/🟡/⚪ 등급 리포트를 만든다. 수정 사항은 **plan만 수정**되고 재승인 후 재생성(버전 +1)된다. |

수정은 **plan 수정 → 새 세대 → 재승인 → 재생성**만이 유일한 경로다. slides.json·report.json·
산출물 파일을 직접 고치는 경로는 존재하지 않는다(설계 원칙 1 — SSOT).

---

## 2. 저장소 구조

```
backend/                  FastAPI 백엔드 + 코어 엔진
  app/                    웹 백엔드 (API·DB·워커·인터뷰 에이전트)
    api/                  REST/SSE 라우터 (projects, sources, interview, plans, reviews, facts, jobs, outputs)
    agents/               인터뷰 상태머신 + LLM 계층 + 프롬프트(prompts/*.md)
    worker.py             단일 백그라운드 워커 (빌드 직렬화 — 멀티 워커 금지)
  planforge/            M1 코어 엔진 (CLI 진입점 `python -m planforge`)
    plan/                 plan.md 파서·문서 필터·골격 검증
    builders/             build_ppt.py · build_doc.py · theme.py (계약 테스트로 고정 — 로직 변경 금지)
    llm/                  OpenAI 호환 provider 추상화
    derive.py, review.py, numcheck.py
  alembic/                DB 마이그레이션
frontend/                 React 19 + TypeScript (Vite)
  src/pages/              ProjectsPage · ProjectPage + 탭 패널 5종
                          (소스·인터뷰·plan·산출물·검수, components/에 CodeMirror 에디터)
  e2e-smoke.mjs           브라우저 e2e 수동 스모크 스크립트 (실제 LLM 사용)
  visual-smoke.mjs        임시 시각 스모크 (스크린샷 확인용)
workspaces/               프로젝트별 워크스페이스 (gitignored — 산출물이 여기 쌓인다)
sources/                  글로벌 소스 (모든 프로젝트가 공유, gitignored)
data/                     SQLite DB (planforge.db, gitignored)
docs/                     보조 문서 (token-checklist.md)
tests/                    pytest (계약 테스트 fixture 포함)
CLAUDE.md                 개발 세션 계약 (설계 원칙 8개)
quick_overview.md         기본 개요 문서 · toons/ 소개 이미지
docker-compose.yml        배포 스택 (backend · frontend · ollama)
```

---

## 3. 빠른 시작 (Docker Compose — 권장)

전제: Docker Desktop(또는 Docker Engine) 설치.

```powershell
# 1) LLM 설정 만들기 (예시 파일을 복사해 모델 지정)
copy backend\planforge\config.example.json backend\planforge\config.json
#   config.json 내용 예: {"profiles": {"interview": {...}, "derive": {...}, "review": {...}}}

# 2) 빌드 및 기동
docker compose build
docker compose up -d

# 3) (ollama 사용 시) ollama 컨테이너 포함 + 최초 1회 인증
docker compose --profile ollama up -d
docker compose --profile ollama exec ollama ollama signin
```

기동 후:

| 화면 | 주소 |
|---|---|
| 웹 UI | http://localhost:5173 |
| 백엔드 API | http://localhost:8000 |
| API 문서(Swagger) | http://localhost:8000/docs |

볼륨: `workspaces/`(산출물) · `sources/`(글로벌 소스) · `data/`(SQLite DB)는 호스트에
남으므로 컨테이너를 재생성해도 유지된다.

> **다른 LLM 프로바이더(openai 등)**: `config.json`의 `base_url`이 compose의
> `LLM_BASE_URL` env보다 우선한다. ollama를 쓰지 않으면 `LLM_BASE_URL`만 바꿔도 된다.
> OpenAI API 키는 서버 환경변수로만 관리한다(브라우저 노출 금지).

---

## 4. 개발 환경 설정 (수동 실행)

전제: **Python 3.12+**, Node.js 20+(Vite 6), Windows는 `PYTHONUTF8=1` 필수.

### 4.1 백엔드

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# LLM 설정 (gitignored — 배포 시점에 확정)
copy planforge\config.example.json planforge\config.json

# DB 스키마 생성 (기본 위치: 저장소 루트 data\planforge.db)
alembic upgrade head

# 개발 서버 기동 (기본 http://localhost:8000)
uvicorn app.main:app --reload
```

### 4.2 프론트엔드 (새 터미널)

```powershell
cd frontend
npm install
npm run dev        # Vite 개발 서버 — /api를 localhost:8000으로 프록시
```

http://localhost:5173 을 열면 된다. 상단에 **"API 연결됨"** 배지가 보이면 정상.

### 4.3 LLM 설정 상세

`backend/planforge/config.json` (gitignored — 예시: `backend/planforge/config.example.json`).
인터뷰·파생·검수·plan 재작성(revise) 각 단계(**프로필**)마다 프로바이더와 모델을
다르게 지정할 수 있다:

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

- 프로바이더는 **OpenAI 호환 단일 프로토콜**(openai SDK)만 사용한다. ollama·openai를
  base_url/키 차이만으로 소화한다. Ollama 모델은 **tool calling 지원이 필수**다.
- `PLANFORGE_CONFIG` 환경변수로 설정 파일 경로를 바꿀 수 있다.
- ollama 외 프로바이더는 `LLM_BASE_URL` env로 base_url을 전환할 수 있다.

---

## 5. 웹 UI 사용 방법 (단계별)

브라우저에서 http://localhost:5173 을 연다. 화면은 **프로젝트 목록 → 프로젝트 탭(5개)** 구조다.

### ① 프로젝트 생성·삭제
- 프로젝트 목록 화면에서 생성 버튼으로 새 프로젝트를 만든다.
- 슬러그는 ASCII 소문자-하이픈만 허용된다 (예: `acme-erp-proposal`).
- 목록의 행별 **삭제** 버튼으로 삭제한다 — 이름 확인 모달 뒤 **영구 삭제**되며
  팩트·plan·산출물·워크스페이스가 모두 함께 제거된다(되돌릴 수 없음).

### ② 소스 등록 ("소스" 탭)
- 기존 기획자료를 업로드한다. 확장자 `.md .txt .json .csv`, 2MB 이하, UTF-8만 허용.
- 같은 이름으로 덮어쓸 수 없다(무덮어쓰기 원칙).
- 여기서 등록한 소스는 **이 프로젝트 전용**이다. 모든 프로젝트가 공유하는 글로벌 소스는
  `sources/` 디렉토리에 파일을 직접 넣는다(`GET /api/sources`로 조회).

### ③ 인터뷰 ("인터뷰" 탭)
1. **인터뷰 시작**을 누르면 에이전트가 소스·기존 팩트를 읽고 **예상 뼈대(가설)를 먼저 제시**한다.
   소스가 텅 비면 초안 없이 뼈대 질문부터 시작한다(임의 추측 금지).
2. 채팅으로 자유롭게 답하거나 **선택지 카드**를 클릭한다. 한 라운드는 최대 4문항.
3. 라운드가 끝나면 **확정 팩트 요약(3~5줄) 확인 다이얼로그**가 뜬다 — 확인을 눌러야만
   팩트가 적립되고 다음 라운드로 간다. 답변과 충돌하는 내용은 조용히 덮지 않고 즉시 물어본다.
4. 라운드 2 이후 **핵심 메시지 3개** 승인 게이트가 나온다. 이후 질문은 이 3개를
   성립시킬 근거 수집을 목표로 한다.
5. 소스가 풍부하면 1~2라운드로 끝나는 것이 정상이다. 체크리스트가 채워지면 인터뷰가 종료되고
   plan 생성 단계로 넘어간다.

### ④ plan 작성·승인 ("plan" 탭)
- 인터뷰에서 만든 plan(마크다운)을 뷰어/에디터로 확인한다. 근거 없는 수치는 `(미확정)`으로 표기된다.
- 표시 방식 토글: **보기**(코드|뷰어 — 뷰어는 렌더링) · **편집**(코드|분할|뷰어 3단) ·
  **diff**(이전 세대 마크다운과 대비, 이전 세대가 없으면 비활성).
- 수정이 필요하면 편집하고 diff를 확인한다.
- **승인 버튼**을 눌러야 파생물 생성이 가능하다. 승인 후 다시 고치면 새 세대(DRAFT)가 만들어지고
  재승인이 필요하다. 이전 승인본은 superseded로 표시된다(세대 추적).

### ⑤ 파생물 생성·다운로드 ("산출물" 탭)
- 생성할 **문서 종류**(제안서/개발설계서 — plan 메타의 산출 문서)를 선택하고 생성 버튼을 누른다.
  1회 실행 = 1문서 (채번 접두어 분리를 위해).
- 작업은 작업 큐(단일 워커)로 처리된다 — 화면에서 진행 상태를 폴링하며 기다린다.
- 완료되면 갤러리에 `output/<문서 제목>_v01.pptx` 같은 파일이 버전별로 쌓인다.
  md·html은 인라인 미리보기, pptx·docx는 다운로드된다. **기존 파일은 절대 덮어써지지 않는다.**
- 하나의 plan에 문서가 여러 개면 `[문서: 제안서+개발설계서]` 태그로 슬라이드가 분리되고,
  각 문서의 목차는 해당 문서만 01..NN으로 재채번된다.

### ⑥ 검수 ("검수" 탭)
- 검수 실행 버튼 → 리포트 1건이 만들어진다:
  - **결정론 검수**: 수치 무결성(plan↔산출물 숫자 대조)·문서 태그·골격 구조·세대 대응(plan 세대 일치 여부)
  - **LLM 내용 검수**: plan↔팩트 대조 (LLM 실패는 리포트를 막지 않고 `llm_ok=false`로 표기)
- 발견사항은 심각도 순: 🔴 사실 오류·수치 불일치 / 🟡 표현·구조 / ⚪ 선택.
- 수정 승인 시 **plan만 수정** → 재승인 → 재생성(버전 +1). 파생물·산출물을 직접 고치는 길은 없다.

### ⑦ 관리
- **팩트 압축**: 인터뷰가 길어지면 `POST /api/projects/{pid}/facts/compact`(미리보기) →
  `.../compact/apply`(활성 팩트 통합 + 이전 항목 아카이브)로 팩트 목록을 정리한다.
  팩트 단건 수정은 `PATCH /api/projects/{pid}/facts/{fact_id}`.

---

## 6. CLI (M1 코어 엔진 — `backend/`에서 실행)

LLM 변환·빌드 파이프라인을 명령줄에서 직접 돌릴 수 있다(웹 UI와 같은 코어를 쓴다).

```powershell
cd backend

# plan 파싱·문서 필터·골격 검증 (표지·목차·마무리·내용 슬라이드 최소 1개씩)
python -m planforge parse <plan.md> [--doc 문서명]

# 수치 무결성 대조 — plan과 산출물의 수치·표·근거 문자열이 한 글자라도 다르면 🔴 (exit 1)
python -m planforge numcheck <plan.md> --slides <slides.json> [--doc 문서명]
python -m planforge numcheck <plan.md> --report <report.json> [--doc 문서명]

# 빌더 원형 직접 실행
python -m planforge build-ppt <slides.json> [output_dir]
python -m planforge build-doc <report.json> <md|html|docx> [output_dir]

# LLM 변환 + 검증 게이트 + 빌드
python -m planforge derive <plan.md> --workspace <dir> --kind slides|report `
    [--doc 문서명] [--fmts md html docx] [--no-build] [--allow-unconfirmed]
```

LLM 설정은 웹과 동일하게 `backend/planforge/config.json`을 읽는다
(예시: `config.example.json`, 기본 ollama — 프로필별 모델 지정 가능).

---

## 7. API 개관

주요 엔드포인트 (전체는 http://localhost:8000/docs 참조):

| 영역 | 엔드포인트 |
|---|---|
| 프로젝트 | `POST/GET /api/projects` · `DELETE /api/projects/{pid}` |
| 소스 | `GET/POST/DELETE /api/projects/{pid}/sources` · `GET /api/sources`(글로벌 읽기전용) |
| 인터뷰(SSE) | `POST .../interview/sessions` → `.../kick` · `.../turn` · `.../answers` · `.../facts/confirm` · `.../key-messages` · `GET .../messages?after=seq` |
| plan | `GET /api/projects/{pid}/plans` · `GET /api/plans/{id}` · `POST /api/plans/{id}/approve` · `POST /api/plans/{id}/revise` |
| 검수 | `POST /api/projects/{pid}/reviews` · `GET /api/projects/{pid}/reviews`(및 단건) |
| 팩트 | `POST /api/projects/{pid}/facts/compact`(미리보기) → `.../compact/apply` · `PATCH .../facts/{fact_id}` |
| 산출물 | `GET /api/projects/{pid}/outputs` · `GET .../outputs/{build_id}/download` |
| 작업 | `GET /api/jobs/{job_id}` · `GET /api/projects/{pid}/jobs` — 202 수락 후 폴링 |

비동기 작업(derive·review 등)은 **202 수락 → job 폴링** 방식이다. 작업은 단일 워커가
직렬 실행한다(빌더의 스레드 안전성 전제 — 멀티 워커는 도입 금지).

---

## 8. 테스트

```powershell
# 저장소 루트에서 (conftest.py가 backend를 import 경로에 추가)
pytest

# 빌더 회귀(계약 테스트) — tests/fixtures/*.sample.json이 빌더 산출물의 동일성을 잠근다
pytest tests/ -k contract

# 수치 무결성 대조 검증
pytest tests/test_numcheck.py
```

- 앱 테스트는 테스트별 tmp_path SQLite DB로 완전 격리된다(`TEST_DATABASE_URL`).
- 워커 루프는 비활성화하고 job은 `run_job` 직접 호출로 결정론 검증한다.
- 테스트 fixture는 반드시 `tests/fixtures/`에 둔다 — `workspaces/`에 쓰면 SSOT 가드 훅이 차단한다.

---

## 9. 운영 배포 (요약)

```powershell
docker compose build && docker compose up -d
# ollama 프로파일: docker compose --profile ollama up -d
#   최초 1회: docker compose --profile ollama exec ollama ollama signin
```

- DB 스키마 변경: `backend/`에서 `alembic revision`으로 마이그레이션 추가 → 배포 시 컨테이너 CMD가
  `alembic upgrade head`를 기동 시 자동 실행한다(개발용 `init_db`는 alembic 대체로만 사용).
- DB는 SQLite 단일 방언(호스트 볼륨 `data/`). WAL + foreign_keys=ON은 연결 리스너가 설정한다.
- 디자인 토큰(색·폰트·여백) 변경 절차: `docs/token-checklist.md` —
  theme.py(기준점) 수정 → tokens.css 미러 수정 → 빌더 리터럴 점검 → 좌표 규격 변경 시
  fixture 갱신. **4종 세트(theme.py·빌더·fixture·tokens.css)를 동시 점검·수정**해야 한다.

---

## 10. 핵심 설계 원칙 (위반 시 구현 자체가 오답 — 상세는 CLAUDE.md)

1. **SSOT**: 콘텐츠 원본은 plan(DB `Plan` 레코드)뿐. 파생물·산출물은 항상 재생성. 직접 수정 금지.
2. **LLM/코드 역할 분리**: LLM은 콘텐츠 변환만. 조립·좌표·채번은 결정론 빌더. LLM이 pptx/docx 바이너리 제작 금지.
3. **수치 무결성**: 수치·표·차트 데이터·`(미확정)`·근거/출처 문자열은 plan과 한 글자도 다르게 복사되지 않는다. 재구성(개조식→서술형)은 문장에만 적용.
4. **팩트 선(先)적립**: 확정 팩트는 DB `Fact`에 먼저 기록 후 plan 반영. 추측 수치는 `(미확정)`.
5. **무손실 채번**: `<문서 제목>_vNN.<ext>`, 확장자별 독립 시퀀스, 절대 덮어쓰기 금지(동시성 포함 — 빌드 직렬화).
6. **다중 문서 태그**: `[문서: 제안서+개발설계서]` 필터링 + 문서별 목차 재채번.
7. **디자인 토큰 4종 세트**: 색·폰트·여백 토큰 변경 시 토큰(theme.py)·렌더러(빌더)·
   샘플(fixture)·프론트 미러(tokens.css) 동시 점검·수정 — 절차는 `docs/token-checklist.md`.
8. **골격 검증**: 파생물 생성 전 표지·목차·마무리·내용 슬라이드 각 1개 이상 검증, 미달 시 중단.

---

## 11. 문제 해결 (FAQ)

**Q. 브라우저에 "API 연결 안 됨"이 보인다.**
백엔드가 기동되지 않은 것이다. `uvicorn app.main:app --reload`(수동) 또는
`docker compose up -d`(배포)로 백엔드를 먼저 띄우고, http://localhost:8000/api/health 가
`{"status":"ok"}`를 반환하는지 확인한다.

**Q. 인터뷰에서 응답이 오지 않는다.**
LLM 설정을 확인한다 — `backend/planforge/config.json`이 있는지, 지정한 모델이
실제로 존재하는지(ollama라면 `ollama list`), **tool calling을 지원하는 모델인지** 확인한다.
Ollama 모델은 tool calling 미지원 시 파생물 생성·도구 호출이 불가능하다.

**Q. DB를 처음부터 다시 만들고 싶다.**
저장소 루트 `data/planforge.db`를 지우고 `backend/`에서 `alembic upgrade head`를 다시
실행한다. `workspaces/`의 파일 트리는 DB와 별개이므로 함께 지우는 것을 권장한다.

**Q. Windows에서 인코딩 에러가 난다.**
`PYTHONUTF8=1` 환경변수가 설정되어 있는지 확인한다(개발·테스트·배포 모두).

**Q. 같은 입력으로 재빌드했는데 파일이 교체되지 않는다.**
정상이다 — 무손실 채번 원칙(원칙 5) 때문에 `v02`가 새로 만들어지고 `v01`은 불변이다.
산출물은 자신이 어떤 plan 세대에서 나왔는지 역참조된다.

**Q. 산출물을 직접 수정하고 싶다.**
설계상 불가능한 것이 맞다(SSOT 원칙 1). 수정은 plan 수정 → 재승인 → 재생성(버전 +1)으로만
처리된다. 이렇게 해야 plan 세대와 산출물 버전의 추적성이 유지된다.