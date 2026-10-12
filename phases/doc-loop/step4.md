# Step 4: interview-doc-threading

## 읽어야 할 파일

먼저 아래 파일들을 읽어라:

- `/CLAUDE.md` — 설계 원칙 계약 + 인터뷰 턴 계약 안내 (계약 4세트 규칙)
- `/docs/INTERVIEW-TURN-CONTRACT.md` — 인터뷰 턴 계약 파일 사이 점검·수정 규칙
  (interview.md 프롬프트 · tools.py 스키마/검증 · 이 문서 · 테스트는 동시 점검)
- `/backend/app/modules/interview/infrastructure/models.py` — InterviewSession
- `/backend/app/modules/interview/facade.py` — complete_plan_review_sessions
- `/backend/app/modules/interview/presentation/api.py` + `schemas.py` —
  create_session·SessionOut·SessionCreate
- `/backend/app/modules/interview/application/agent.py` — `_write_plan`(~314행),
  `commit_facts`(~355행), `_system_prompt`/`_turn_context` 구조
- `/backend/app/agents/tools.py` — `update_checklist` 도구의 area 설명 문자열
  (~138행: "area는 공통|제안서|개발설계서 중 하나" — 검증자는 hard enum이 아니다)
- `/backend/app/modules/interview/application/prompts/interview.md` — area 어휘 언급 위치
- `/backend/app/modules/docloops/facade.py` + `application/service.py` — step 2 산출물
  (require_session_doc, has_doc_layout)
- `/backend/app/modules/plans/facade.py` — step 3에서 `create_generation(..., doc_slug=None)`
  파라미터가 추가됐다
- `/backend/app/shared/workspace.py` — step 1 산출물 (doc_ws_root, ensure_doc_ws,
  DOC_WS_SUBDIRS)
- `/tests/test_interview_api.py` — 기존 인터뷰 계약 테스트 (회귀 기준)

이전 step 산출물은 `phases/doc-loop/step{0..3}-output.json`의 summary로 확인하라.

## 작업

인터뷰 세션에 문서 정체성(doc_slug)을 스레딩한다. 기능 배경: 각 문서 버튼이 자체
인터뷰 루프를 가지며, 세션은 자기 문서의 워크스페이스
(`workspaces/{프로젝트slug}/{문서slug}/`)에 미러를 쓰고, 이 문서의 plan 세대에는
`doc_slug`가 새겨진다. `doc_slug`가 없는 세션(None)은 레거시 세션이다 — 기존
프로젝트·기존 화면 흐름이 전부 그대로 동작해야 한다.

### 1. 세션 doc 필드

- `interview/infrastructure/models.py` `InterviewSession`에
  `doc_slug: Mapped[str | None] = mapped_column(String(32), nullable=True)` 추가.
- `interview/presentation/schemas.py`:
  - `SessionCreate`에 `doc_slug: str | None = None`
  - `SessionOut`에 `doc_slug: str | None`
- `interview/presentation/api.py create_session`:
  1. `body.doc_slug`가 있으면 `docloops.facade.require_session_doc(db,
     project_id, body.doc_slug)`를 통과시킨다 (미상 404 · locked 409 — step 2 계약).
  2. 세션을 `InterviewSession(project_id=project_id, doc_slug=...)`로 생성.
  3. 문서 세션 생성 시점 = 해당 문서 루프의 시작. `docloops.facade.has_doc_layout`
     (doc_loops 행 권위)이 True고 doc_slug 세션이면
     `app.shared.workspace.doc_ws_root(Path(project.workspace_path), doc_slug,
     doc_layout=True)` → `ensure_doc_ws(root)`로 지연 생성한다.
     `project`는 `projects.facade.require_project` 경유로 얻는다.
     (레거시 프로젝트 — 行 없음 — 에서 doc 세션을 만들면 409/404가 아니라 slug만 저장되고
     미러는 루트 경로를 유지한다. 기존 프로젝트 무이관 계약.)

### 2. 세션 완료 처리의 문서 스코프

`interview/facade.py complete_plan_review_sessions`:

```python
def complete_plan_review_sessions(db: Session, project_id: int,
                                  doc_slug: str | None = None) -> None:
    """doc_slug를 주면 그 문서 세션만, 주지 않으면 기존 동작(전체)을 유지한다."""
```

- doc_slug 주어짐 → `.where(... == doc_slug)`만 추가된 WHERE.
- 기본(None)은 기존 쿼리 그대로 — 기존 호출자(레거시 plan 승인) 동작 보존.
  plans 서비스는 step 5에서 doc plan 승인 시 slug를 명시적으로 넘긴다.

### 3. agent — 세대·미러에 doc 반영

`interview/application/agent.py`:

- `_write_plan` (~340행): `create_generation(...)` 호출에
  `doc_slug=self.sess.doc_slug` 전달. 미러는
  `app.shared.workspace.doc_ws_root(Path(self.sess.project.workspace_path),
  self.sess.doc_slug, doc_layout=docloops.facade.has_doc_layout(self.db,
  self.sess.project_id))`로 결정한 root에 `write_plan_mirror(ws_root, md)` 실행.
  (doc 없는 세션은 None → doc_ws_root가 `ws`를 반환 — 기존 경로 동일.)
- `commit_facts` (~355행): `write_interview_log_mirror`에 같은 ws_root 결정식을
  적용한다. **facts 적립(`append_facts`) 자체는 변경하지 않는다** — 팩트는 프로젝트
  공유 저장소 유지가 설계 결정이다(Fact는 세션 귀속이므로 doc 구분은 session_id로 가능).
- 참고: `compact`(facts 모듈)는 이번 기능에서 워크스페이스 루트 미러를 유지한다 —
  문서별 컴팩트 미러는 범위 밖((미확정) 기록).
- import 경계: agent는 `docloops.facade`를 import해도 된다 (interview → doclops 방향).

### 4. 인터뷰 계약 어휘 확장 (경량 — 계약 4세트 동시 점검)

UI·UX설계서가 plan 본문 문서 어휘로 나타날 수 있는 지점을 함께 정리한다:

- `/backend/app/agents/tools.py` `update_checklist` 도구 설명 문자열의 area 어휘
  ("공통|제안서|개발설계서") — 검증자로는 hard enum이 아니므로 설명 문자열만
  "공통|제안서|UI·UX설계서|개발설계서"로 확장.
- `/backend/app/modules/interview/application/prompts/interview.md` — area 어휘 언급이
  있는 절을 동일하게 확장 (기존 어휘 표기 위치를 찾아 동일 규칙 적용).
- `/docs/INTERVIEW-TURN-CONTRACT.md` — area 어휘에 대한 언급이 있으면 동시 수정.
  (이 계약 4개 표면 — 프롬프트·tools.py·문서·테스트 — 는 하나만 고치면 반려다.)
- 테스트는 기존 `tests/test_interview_api.py`의 contract 테스트가 회귀 기준.

### 5. 테스트 추가

`tests/test_docloops_api.py`에 다음 케이스를 추가한다 (step 3에서 만든 파일):

- `POST /api/projects/{id}/interview/sessions` 본문 `{"doc_slug": "proposal"}` → 201,
  `doc_slug="proposal"`이고 `workspaces/{slug}/proposal/{work,output,docs,assets}`
  4개 디렉토리가 생성됨 (db_env 워크스페이스 경로에서 확인)
- locked 문서 `{"doc_slug": "uiux-design"}` → 409, 안내 메시지 확인
- 미상 문서 `{"doc_slug": "nonsense"}` → 404
- 본문 없는 세션(None doc) → 201, `doc_slug` null, 문서별 디렉터리 생성 안 함
- 프로젝트 세션 완료 스코프: doc_slug="proposal" plan 승인은 step 5에서 수행되므로
  이 step에서는 `complete_plan_review_sessions(db, pid, doc_slug="proposal")`의
  narrowing이 (동일 프로젝트에 proposal·uiux 세션을 시드해) proposal 세션만
  완료함을 직접 검증하는 케이스를 `tests/test_docloops_service.py` 또는
  `tests/test_interview_api.py`에 둔다.

## Acceptance Criteria

```bash
python -m pytest tests/test_docloops_api.py tests/test_docloops_service.py tests/test_interview_api.py -q   # 저장소 루트에서
```

기존 `test_interview_api` 전체가 무수정 통과해야 한다 (doc_slug 기본 None이라 프론트
기존 화면·기존 테스트 흐름에 영향이 없어야 한다).

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트:
   - interview → docloops/plans 모듈 접근이 facade 경유인가?
   - 인터뷰 계약 4세트(tools.py · interview.md · INTERVIEW-TURN-CONTRACT.md · 테스트)
     를 이 step 안에서 모두 점검했는가? (하나만 고치면 반려)
3. 결과에 따라 `/phases/doc-loop/index.json`의 해당 step을 업데이트한다
   (completed + summary — step 5가 `complete_plan_review_sessions` 새 파라미터와
   세션 doc 필드를 이어받을 수 있게 명시).

## 금지사항

- `complete_plan_review_sessions`의 기본 동작(None = 전체)을 변경하지 마라 — 이유:
  레거시 plan 승인 경로와 기존 테스트 계약이 그 동작에 고정돼 있다.
- 팩트 저장소(facts 모듈)의 프로젝트 공유 구조 변경 금지 — 이유: 문서 간 공유 팩트는
  plan 상호 참조(Phase 2)의 전제이며, 이번 기능 확정 범위는 미러 분리뿐이다.
- `SessionCreate`에 doc_slug 검증(404/409) 없이 세션을 생성하는 하위호환 우회
  (예: 다른 엔드포인트 추가) 금지 — 이유: 세션 게이트는 문서 루프 상태머신의 권위
  지점이고 우회하면 locked 문서 인터뷰가 우회 생성된다.
- `_write_plan`의 검증 체인(parse_plan_text → 핵심메시지 3개 → 골격) 변경 금지 —
  이유: 수치·골격 무결성 계약. 이 step은 세대 doc slug/미러 경로만 바꾼다.
- plan 마크다운 어휘(`- 산출 문서:` 한글 이름)의 파서측 강제 변경 금지 — 이유:
  planforge 파서는 임의 문서명을 허용하는 것이 계약이고 빌더 로직 변경은 금지 계약이다.
- `workspaces/` 아래 직접 쓰기 금지 (SSOT 가드훅) — fixture는 tmp_path·db_env.