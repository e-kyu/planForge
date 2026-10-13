# Step 0: derive-doc-slug-guard — 파생물 생성 API에 doc_slug 계약 강화 (백엔드 + 테스트)

## 배경 (자기완결 — 외부 대화 참조 금지)

doc-loop 이후 문서별 승인 plan이 공존할 수 있다(`_scoped_supersede` — projects application
service의 콘셉트). 그런데 파생물 생성 API `POST /api/projects/{pid}/derivatives`는
요청 `doc_slug`가 None이면 `plans/facade.py latest_approved`가 **프로젝트 전체
version_no 최대 승인 plan 1건**을 무차별 선택한다. 래치(docloops on_plan_approved —
proposal 승인 → 다음 문서 active → 승인) 순서상 나중에 승인된 문서의 plan이 항상
최신이므로, doc-loop 프로젝트에서 doc_slug 없이 생성 요청을 날리면 **의도와 다른
문서의 plan**으로 산출물이 만들어진다 (derive_build는 plan.doc_slug 권위로 ws 경로·
Build.doc_slug를 기록).

실버그: 두 문서 루프(제안서·UI·UX설계서) 모두 done인 프로젝트에서 제안서 산출물을
생성하면 UI·UX 산출물만 생성된다. 프론트가 요청에 doc_slug를 싣지 않은 것이 근본
원인(step 1 소관) — 이 step은 백엔드 방어 가드로 오문서 선택을 원천 차단하고,
계약 위반을 명시적 에러로 드러낸다.

**계약 원칙**: 레거시(doc_loops 행이 없는) 프로젝트는 기존 None 허용 계약을 유지한다.
doc-loop 프로젝트(`docloops.has_doc_layout`)는 doc_slug 필수이며, 미상 doc_slug는
거부한다. 실행 시점 권위는 여전히 plan 행(plan.doc_slug) — 가드는 plan **선택**을
바로잡을 뿐 큐 payload·실행 계층 계약은 건드리지 않는다.

## 읽어야 할 파일

- `/CLAUDE.md`, `/backend/CLAUDE.md`
- `/docs/ADR.md` — 결정 22(doc-loop) 문맥
- `/backend/app/modules/derivatives/presentation/api.py` — 주 대상
  (`enqueue_derivative`, `docloops` facade가 이미 import돼 있다)
- `/backend/app/modules/docloops/facade.py` — `has_doc_layout`·`DOC_KINDS` 공개 함수 확인
- `/backend/app/modules/plans/facade.py` — `latest_approved` 계약(None=문서 무관) 확인
- `/backend/app/modules/derivatives/application/derive_build.py` — 읽기 전용(plan.doc_slug 권위 이해)
- `/tests/_helpers.py` — `make_project`, `insert_plan`, `run_derive` 헬퍼
- `/tests/test_docloops_api.py`, `/tests/test_jobs_worker.py`, `/tests/test_review.py`,
  `/tests/test_enqueue_visibility.py`, `/tests/test_interview_api.py` — 갱신 대상

## 작업

### 1. `backend/app/modules/derivatives/presentation/api.py` — 가드 추가

`enqueue_derivative`의 kind·fmts 검증 뒤, `latest_approved` 앞에:

```python
if body.doc_slug is None and docloops.has_doc_layout(db, project_id):
    raise http_409("문서 루프 프로젝트에서는 doc_slug를 지정해야 합니다")
if body.doc_slug is not None and body.doc_slug not in {s for s, _ in docloops.DOC_KINDS}:
    raise http_404(f"알 수 없는 문서 slug입니다: {body.doc_slug}")
```

- 상태코드: 누락 409(이 엔드포인트 kind·fmts 검증의 기존 관례), 미상 slug 404
  (`require_session_doc`의 기존 관례와 정합). 파일의 기존 에러 응답 헬퍼/패턴을 그대로 따른다.
- 모듈 경계: docloops는 facade 공개 함수(`has_doc_layout`·`DOC_KINDS`) 경유만.
- 계약 주석 갱신 (기존 "doc_slug가 주어지면 ..." 주석 부근):
  "doc-loop 프로젝트(has_doc_layout)는 doc_slug 필수 — None fallback은 문서별 승인본
  공존 하에 래치 순서상 오문서 plan을 고른다. 레거시(루프 행 없음)만 None 허용.
  실행 시점 권위는 여전히 plan 행(plan.doc_slug)". 기존 "큐 payload에는 doc_slug를
  싣지 않는다" 주석의 payload 계약 부분은 유지한다.

### 2. `docs/ADR.md` — 결정 기록

결정 22(doc-loop) 블록의 하위 기록 위치에 2~3줄 추가: "파생물 enqueue는 doc-loop
프로젝트에서 doc_slug 필수(누락 409·미상 404) — None fallback이 문서별 승인본 공존
하에 래치 순서상 오문서 plan을 고르는 결함 수정. 레거시는 None 허용 계약 유지."

### 3. 기존 테스트 갱신 — **body와 시드 plan 둘 다** 갱신 원칙

`make_project`(POST /api/projects)로 만든 프로젝트는 생성 시 `init_project_loops`로
루프 3행이 시드돼 `has_doc_layout=True`다. 따라서 (a) 요청 body에
`"doc_slug": "proposal"`를 실고 (b) 시드 plan(`insert_plan`)에도 `doc_slug="proposal"`
여야 `latest_approved`가 plan을 반환한다 — 둘 중 하나만 바꾸면 plan이 None이 되어
409 없는 빈 결과나 어설션 파손이 생긴다.

- `tests/test_jobs_worker.py` — POST /derivatives 10곳 + 짝 insert_plan 갱신.
  `test_unapproved_plan_blocks_derive`도 body에 doc_slug를 실어야 한다 — 미실으면
  에러 메시지가 "doc_slug 필요"로 바뀌어 "승인" 어설션이 실패한다.
- `tests/test_review.py` — `tests/_helpers.py run_derive`에 `doc_slug: str | None = None`
  kwarg 추가(값이 있으면 body에 실음), 5개 호출부에서 `"proposal"` 전달 + 시드
  insert_plan 4곳 갱신.
- `tests/test_enqueue_visibility.py` — POST 1곳 + 시드 plan 갱신.
- `tests/test_interview_api.py` — `test_interview_to_build_end_to_end`의 세션을
  proposal 문서 세션으로 만들어 write_plan이 plan.doc_slug를 심게 한다(세션 생성 body에
  `doc_slug: "proposal"`; 제안서 루프는 생성 직후 active라 게이트 통과). 산출물 경로
  어설션도 문서 세션의 doc ws 루트(`workspaces.../proposal/`)를 반영해 갱신한다
  (mirror root는 `doc_ws_root`가 결정 — `app/shared/workspace.py` 참고).
- `tests/test_docloops_api.py`:
  - `test_outputs_doc_slug_filter` 전후 — doc_slug=None derive 케이스가 가드로 막히는
    부분을 doc_slug를 실어 보내는 방향으로 재작성(둘 다 doc Slug 상이한 두 문서의
    plan을 시드하고 각 doc_slug로 derive — doc별 필터 동작 검증 유지).
  - **신규 가드 테스트**: doc-loop 프로젝트에서 doc_slug 없이 POST → 409 + 메시지
    검증, 미상 slug(`"unknown-doc"`) → 404 검증. 레거시(루프 행 삭제) 프로젝트는
    None 허용임을 이미 고정하는 `test_legacy_doc_none_derive_uses_project_root`가
    있으니 회귀 없음을 AC에서 확인한다.

## Acceptance Criteria

```bash
python -m pytest tests/test_docloops_api.py tests/test_jobs_worker.py tests/test_review.py tests/test_enqueue_visibility.py tests/test_interview_api.py -q   # 저장소 루트, backend/.venv 인터프리터, PYTHONUTF8=1
```

## 검증 절차

1. 위 AC 커맨드를 실행해 통과(0 failed)를 확인한다.
2. 아키텍처 체크리스트:
   - docloops 접근은 facade 공개 함수 경유만 (`has_doc_layout`·`DOC_KINDS`).
   - `planforge/`·`derive_build.py`를 수정하지 않았는가? — 가드는 presentation 계층이다.
   - `plans/facade.py latest_approved` 계약(None=문서 무관)을 유지했는가? — 가드는 호출자(api.py) 책임.
   - CLAUDE.md 설계 원칙 위반 없는가?
3. `phases/derive-doc-slug/index.json`의 step 0 status를 업데이트한다
   (성공 → `"completed"` + `"summary"`에 갱신한 파일·테스트 수·새 테스트명 한 줄).

## 금지사항

- OpenAPI 재export(`scripts/export_openapi.py`)·`frontend npm run gen:types` 실행
  금지 — 이유: `DerivativeCreate.doc_slug`는 이미 optional로 존재하고 가드는 런타임
  에러 응답뿐이라 OpenAPI 스키마가 불변이다. 불필요한 export는 계약 diff 노이즈를
  만든다 (`git diff -- backend/app/openapi.json`이 비어야 정상).
- `DerivativeCreate` 스키마·모델·마이그레이션을 수정하지 마라 — 이유: 계약 필드는
  이미 있고 이번 결함은 검증 누락이다.
- `backend/app/modules/derivatives/application/derive_build.py`·`planforge/` 수정
  금지 — 이유: plan 선택이 올바르게 고정되면 실행 계층은 그대로 정답이다.
- 레거시 프로젝트(루프 행 없음)의 None 허용을 바꾸지 마라 — 이유: 기존 계약 유지가
  이 step의 전제며 `test_legacy_doc_none_derive_uses_project_root`가 이를 고정한다.
- 워크스페이스 파생물(`workspaces/**`)을 직접 쓰지 마라 — 이유: SSOT 가드훅 정상 차단.
- 기존 테스트를 깨뜨리지 마라 — 갱신은 위 원칙(body+seed 둘 다)을 따른다.