# Step 6: derive-review-doc-ws

## 읽어야 할 파일

먼저 아래 파일들을 읽어라:

- `/CLAUDE.md` — 설계 원칙 계약 (원칙 1 SSOT·원칙 3 수치 무결성·원칙 5 무손실 채번·
  결정 17 numcheck 게이트·빌더 로직 변경 금지)
- `/backend/app/modules/derivatives/application/derive_build.py` — derive_build job
  핸들러 (ws 결정·미러·Deriver·atomic_build·Build 행)
- `/backend/app/modules/derivatives/presentation/api.py` + `schemas.py` —
  enqueue·outputs·download (Build.file_path가 워크스페이스 상대경로 계약)
- `/backend/app/modules/derivatives/facade.py` — list_builds 등
- `/backend/app/modules/review/application/run_review.py` — 검수의 세대 대응성 점검
  (§2, 69행 근처)·팩트 대조
- `/backend/app/modules/plans/facade.py` — step 3 산출물 (`latest_approved(doc_slug)`)
- `/backend/app/modules/docloops/facade.py` — step 2 산출물 (`has_doc_layout`)
- `/backend/app/shared/workspace.py` — step 1 산출물 (`doc_ws_root`, `atomic_build`,
  `parse_build_filename`)
- `/tests/test_jobs_worker.py` — job 결정론 검증 패턴 (run_job 직접 호출)
- `/tests/test_derivatives_api.py`, `/tests/test_review.py`, `/tests/test_derive.py`

이전 step 산출물은 `phases/doc-loop/step{0..5}-output.json`의 summary로 확인하라.

## 작업

파이프라인 실행부(derive·build·검수)에 문서별 워크스페이스를 반영한다.
기능 배경: 각 문서 루프의 파생물과 산출물은 자기 문서의
`workspaces/{프로젝트slug}/{문서slug}/work|output`에 쌓인다. 빌더 로직은 한 글자도
바꾸지 않고 **주입되는 경로만** 바꾼다 (변경 금지 계약 — planforge 엔진은 이 step에서
수정 대상이 아니다). `Build.file_path`는 여전히 "output/..." 형식으로 워크스페이스
루트 기준이 아니라 **문서별 ws 루트 기준 상대경로**를 유지한다 (기존 계약 형식 보존).
레이아웃 권위는 doc_loops 행이라 doc_slug=None plan은 기존과 같이 프로젝트 루트를 쓴다.

### 1. derive_build job — `backend/app/modules/derivatives/application/derive_build.py`

`run_derive_build` 변경 (기존 흐름·진행 기록 불변식 유지):

1. ws 결정을 교체:
   ```python
   ws_root = doc_ws_root(Path(project.workspace_path), plan.doc_slug,
                         doc_layout=has_doc_layout(session, plan.project_id))
   ```
   (`has_doc_layout`은 `docloops.facade` 경유). 이후 `write_plan_mirror`·
   `Deriver(chat_fn, ws_root)`·`atomic_build(ws_root, run_builder)`가 전부 이 root를
   쓴다.
2. `Build(...)` 생성 시 `doc_slug=plan.doc_slug` 컬럼을 채운다 (builds 테이블 —
   step 0에서 컬럼 추가됨).
3. 그 외의 것(LDeriver 계약·진행 기록 불변식·세대 결정·numcheck·자동 검수 큐잉)은
   변경하지 않는다.

### 2. enqueue API — `backend/app/modules/derivatives/presentation/api.py`

- `DerivativeCreate`(`schemas.py`)에 `doc_slug: str | None = None` 추가.
- `enqueue_derivative`: `body.doc_slug`가 주어지면 게이트 plan을
  `latest_approved(db, project_id, doc_slug=body.doc_slug)`로 조회 (step 3 파라미터),
  None이면 기존 계약(`latest_approved` 전체 프로젝트 기준) 그대로. 큐 payload에
  `doc_slug`는 **plan 행이 권위이므로 실어 보내지 않는다** — job 실행 시
  `plan.doc_slug`를 읽어 경로를 결정한다 (큐 시점과 실행 시점 plan 스코프 일치).
- `list_outputs`: 선택적 `doc_slug: str | None = Query(default=None)` — 주어지면
  `Build.doc_slug == doc_slug` 필터. 파일 존재 확인 경로를
  `doc_ws_root(Path(project.workspace_path), b.doc_slug, doc_layout=has_doc_layout
  (db, project_id)) / b.file_path`로 결정해 보정한다.
- `download_output`: 동일한 식의 경로 결정으로 파일을 찾는다.

### 3. 검수 — `backend/app/modules/review/application/run_review.py`

1. 미러 root를 `doc_ws_root(... plan.doc_slug ... doc_layout=has_doc_layout(session,
   project.id))`로 결정 (write_plan_mirror·parse_plan_file에 동일 반영).
2. §2 세대 대응성 점검(69행 근처 `list_builds`)을 문서 스코프로 좁힌다:
   `plan.doc_slug`가 None이면 기존(전체 빌드), 아니면 `b.doc_slug != plan.doc_slug`
   빌드를 스킵. 이유: 다른 문서의 산출물이 "이전 plan 세대" red 오탐으로 잡히는 것을
   제거해야 하고, 문서 스코프의 세대 판정은 이 plan의 문서 빌드에만 유효하다.
   §1(파생물 대조) 등 나머지 검수 로직은 변경 금지.

### 4. 테스트

`tests/test_docloops_api.py`에 추가 (job은 `run_job` 직접 호출 패턴 —
`tests/test_jobs_worker.py` 참조, worker 루프는 비활성 상태가 conftest 계약):

1. doc_slug="proposal" plan 승인 후 `POST /api/projects/{id}/derivatives` 본문
   `{"kind": "slides", "doc_slug": "proposal", "fmts": ["md"]}` → 202 → run_job →
   `workspaces/<slug>/proposal/work/slides.json` + `proposal/output/<title>_v01.md`
   생성, `Build.doc_slug == "proposal"`, `file_path`가 "output/..." 형식 유지.
2. `GET /outputs`와 download가 문서 경로에서 파일을 찾는지 확인 (list_outputs가
   결과를 반환하고, 다운로드 200).
3. `?doc_slug=proposal` 필터 동작.
4. 검수: `enqueue_auto_review`/검수 job을 run_job으로 실행해 문서 스코프 밖 빌드
   (doc_slug=None 시드 빌드 등)가 "이전 plan 세대" red를 만들지 않음 검증 — 대신
   `run_review`의 narrowing만 직접 시드로 검증하는 케이스로 단순화해도 된다.
5. 회귀: doc_loops 행 없는 프로젝트 + doc_slug=None plan의 derive는 기존과 동일하게
   프로젝트 루트 work/output을 쓴다 (`test_jobs_worker`·`test_derivatives_api`가
   무수정 통과하는 것으로 확인).

LLM fake 주입은 `JobContext(llm_overrides=...)` 계약을 따른다 (conftest 계약).

## Acceptance Criteria

```bash
python -m pytest tests/test_jobs_worker.py tests/test_derivatives_api.py tests/test_review.py tests/test_docloops_api.py -q   # 저장소 루트에서
```

기존 job·derive·review 테스트 전부 무수정 통과해야 한다.

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트:
   - `planforge/**`(Deriver·빌더·numcheck)을 수정하지 않았는가? (경로 주입만 — 변경
     금지 계약)
   - `Build.file_path`가 여전히 "output/..." 상대 형식인가? (계약 유지)
   - 진행 기록 불변식(report_progress는 대기 중 도메인 행 없을 때만)을 유지했는가?
3. 결과에 따라 `/phases/doc-loop/index.json`의 해당 step을 업데이트한다
   (completed + summary — 백엔드 파이프라인 종료 선언).

## 금지사항

- `planforge/derivative.py`·`planforge/builders/*` 로직 변경 금지 — 이유: 바이트 동일
  이식본·결정론 빌더 변경 금지 계약. 경로는 외부(workspace 주입)만 바꾼다.
- `Build.file_path`의 "output/" 접두 계약을 절대 경로나 문서별 접두로 바꾸지 마라 —
  이유: 기존 rows·다운로드 결합 계약과 `parse_build_filename`의 규약 유지.
- enqueue 시점의 plan doc_slug를 payload에 스냅샷으로 싣는 것 금지 — 이유: job 실행 시점
  승인 plan 권위는 `latest_approved` 결과 행이며, 이중 권위는 미정합을 만든다.
  (실행 시점에 plan.doc_slug를 읽는 것으로 충분하다.)
- 검수 §1(파생물↔plan 대조)·§3(태그)·§4(팩트)·§5(LLM) 로직 변경 금지 — 이유: 결정 17의
  게이트·원칙 3 수치 무결성. 이 step은 세대 대응성(§2)의 스코프만 좁힌다.
- 병렬 워커· 멀티스레드 빌드 도입 금지 — 이유: 빌더가 스레드 안전하지 않고 단일 워커
  직렬 계약이다.
- `workspaces/` 아래 직접 쓰기 금지 (SSOT 가드훅) — fixture는 tmp_path·db_env.