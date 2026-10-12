# Step 5: plans-doc-threading

## 읽어야 할 파일

먼저 아래 파일들을 읽어라:

- `/CLAUDE.md` — 설계 원칙 계약 (원칙 1 SSOT — plan 수정은 revise→새 세대→재승인만
  유일 경로; 승인 게이트)
- `/backend/app/modules/plans/application/service.py` — `approve_plan`·`revise_plan`
  (이 기능의 유일한 승인 훅 지점)
- `/backend/app/modules/plans/application/plan_revise_job.py` — 검수 반영 job
- `/backend/app/modules/plans/facade.py` — step 3 산출물 (`create_generation(
  doc_slug=None)`, `latest_approved(doc_slug=None)`, `latest_generations_by_doc`)
- `/backend/app/modules/interview/facade.py` — step 4 산출물
  (`complete_plan_review_sessions(db, project_id, doc_slug=None)`)
- `/backend/app/modules/docloops/facade.py` — step 2 산출물 (`on_plan_approved`,
  `has_doc_layout`)
- `/backend/app/shared/workspace.py` — step 1 산출물 (`doc_ws_root`)
- `/backend/app/modules/plans/presentation/api.py` — approve·revise 엔드포인트
- `/tests/test_plans_api.py` — `test_approve_flow_and_supersede`(18-43행)이 회귀 기준
  (프로젝트 전체 승인본 1개 불변식의 레거시 계약)

이전 step 산출물은 `phases/doc-loop/step{0..4}-output.json`의 summary로 확인하라.

## 작업

plan 승인(Approve)을 문서 스코프로 좁히고, 승인 트랜잭션 안에서 문서 루프를 진행시킨다.
기능 배경: 완료 판정 = plan 승인. proposal plan이 승인되면 proposal 루프가 done이 되고
uiux-design 버튼(active)이 열린다. 기존 코드는 "프로젝트당 승인본 1개" 불변식을 위해
같은 프로젝트의 모든 승인 plan을 SUPERSEDED로 전역 전이했다 — 이 것이 이 기능의
핵심 스키마 변경 지점이며, **문서 스코프로 좁히는 것**이 요구사항이다.

### 1. 승인 스코프 좁힘 — `plans/application/service.py`

```python
def _scoped_supersede(db: Session, plan: Plan) -> None:
    """이전 승인본은 문서 스코프내 세대 교체 — 유효한 SSOT 승인본은 문서당 최신 하나."""
```

- 기존 전역 쿼리(프로젝트 승인 plan 전부 SUPERSEDED)를 다음으로 교체:
  - `plan.doc_slug is None` → `Plan.doc_slug.is_(None)` 조건으로 좁힌다
    (NULL 매칭은 SQL equality로는 안 잡힌다 — 명시 분기 필수).
  - `plan.doc_slug` 주어짐 → `Plan.doc_slug == plan.doc_slug`로 좁힘.
- 효과: proposal 승인본이 유지되는 상태에서 uiux plan 승인이 가능해진다. 문서별로는
  여전히 "승인본 1개" 불변식이 유지된다.

`approve_plan` 변경:

1. `_scoped_supersede`로 교체 (기존 루프 삭제).
2. 세션 완료: `complete_plan_review_sessions(db, plan.project_id, doc_slug=plan.doc_slug)`
   — 단, `plan.doc_slug is None`이면 **파라미터를 넘기지 않는다**(기존 동작 = 전체).
   step 4의 facade 시그니처 계약 그대로.
3. 미러: `ws_root = doc_ws_root(Path(project.workspace_path), plan.doc_slug,
   doc_layout=docloops.facade.has_doc_layout(db, plan.project_id))` →
   `write_plan_mirror(ws_root, plan.markdown)`.
4. 루프 진행 훅: `docloops.facade.on_plan_approved(db, plan.project_id, plan.doc_slug)`
   — **db.commit() 전, 승인 트랜잭션 내부**에서 호출해 원자성을 유지한다.
   (행 없는 프로젝트는 facade가 no-op — 기존 프로젝트 안전.)

`revise_plan` 변경: `create_generation(..., doc_slug=base.doc_slug)` 유지 +
미러 root를 위와 동일한 `doc_ws_root` 식으로 결정.

`plan_revise_job.py` 변경: `create_generation(..., doc_slug=plan.doc_slug)` +
미러 root 결정 동일 (job 세션에서 `has_doc_layout(session, plan.project_id)`).

### 2. 승인·수정 게이트는 문서별로 재활용한다 — 계약 명시

- DRAFT가 아니면 409, DRAFT가 아니면 파생 단계로 넘어가지 않는다는 기존 게이트는
  유지한다.
- version_no는 **프로젝트 전체 단조**를 유지한다 (`uq_project_planver` — 무손실 채번
  계약; 문서별 재채번은 (미확정) 기록되어 phase 범위 밖).

### 3. 검수 세션 완료 스코프 연동

`approve_plan`이 넘기는 `doc_slug`로 인해 (step 4의 narrowing) 같은 프로젝트에서
proposal 세션이 완료되어도 uiux 세션의 PLAN_REVIEW 페이즈는 절대 건드리지 않는다.
이 동작은 테스트로 검증한다 (아래 4-3).

### 4. 테스트

`tests/test_docloops_api.py`에 추가 (step 3·4에서 만든 파일). plan 시딩은
`tests/_helpers.insert_plan`을 쓴다 (status·doc_slug 지원 확인 후 사용 — 필요하면
helper에 doc_slug 파라미터를 추가한다):

1. 승인 전파: `proposal` doc plan을 `POST /api/plans/{id}/approve` → proposal 루프
   done, uiux-design active, dev-design locked. 이어 uiux plan 승인 → dev-design active.
2. 래치: proposal 새 세대(create doc_slug=proposal plan → 승인) 재승인에도
   uiux-design·dev-design가 active 유지, doc_loops 행은 3개 유지.
3. 세션 스코프: proposal plan 승인 시 plan_review인 세션 중 uiux 세션은 페이즈가
   UNCHANGED임을 검증 (interview 세션 시드 후).
4. 문서별 미러: proposal plan 승인 → `workspaces/<slug>/proposal/plan.md` 존재,
   루트 `plan.md`는 doc_loops 행이 있는 프로젝트에서 **없음**(doc 세션 미러 경로가
   루트가 아님이 검증됨). `plan.doc_slug=None` plan 승인 시 루트 미러가 생성됨(레거시).
5. supersede 스코프: proposal v1 승인 후 uiux plan도 승인한 상태에서 proposal v2
   승인 → proposal v1은 superseded, **uiux 승인 plan은 APPROVED 유지**.
6. `?doc_slug=` 필터: `GET /api/projects/{id}/plans?doc_slug=proposal` → proposal
   세대만. 없는 필터는 전체(기존).
7. 레거시 회귀: doc_loops 행 없는 프로젝트 시드 시의 승인·미러가 전부 루트 경로로
   동작함 (DB 시드 기준 — doc_loops delete 후 재검증).

`tests/test_plans_api.py::test_approve_flow_and_supersede`가 **무수정 통과**해야 한다 —
doc=None plan의 승인 전이는 NULL 스코프로 좁혀져 기존 동작과 동일해야 한다.

## Acceptance Criteria

```bash
python -m pytest tests/test_plans_api.py tests/test_docloops_api.py tests/test_docloops_service.py tests/test_interview_api.py -q   # 저장소 루트에서
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트:
   - `approve_plan`이 승인 트랜잭션 내에서 docloops 훅을 호출하는가? (커밋 전 필수)
   - docloops 훅의 멱등·래치 의미를 service 계약대로 유지히면서 plans 단에서 우회
     (루프 행 직접 수정) 하지않았는가?
   - CLAUDE.md 원칙 1(수정 경로 uniqueness)·원칙 5(채번)를 위반하지 않는가?
3. 결과에 따라 `/phases/doc-loop/index.json`의 해당 step을 업데이트한다
   (completed + summary — 승인 전파 완성이 이 step의 핵심 산출이다).

## 금지사항

- 승인 전이 전에 파생물 생성을 허용하는 것 금지 — 이유: FR 승인 게이트 계약.
- `uq_project_planver` 제약·채번 재구성 금지 — 이유: version_no는 프로젝트 전체
  단조 유지가 확정 결정이다 (문서별 재채번은 (미확정) 기록).
- 승인 트랜잭션 밖(커밋 후)에서 docloops 훅을 호출하는 것 금지 — 이유: 승인과 루프
  진행이 분리되면 승인은 됐는데 루프가 열리지 않는 미정합 상태가 생긴다.
- `plan.doc_slug is None`을 SQL equal(`== None`)로 매칭하는 것 금지 — 이유: SQL에서
  `NULL = NULL`은 거짓이라 레거시 승인본이 SUPERSEDED로 전이되지 않는다
  (`is_(None)` 명시 분기가 필수).
- plan 미러를 문서 경로로 쓰면서 레거시 plan(None)은 루트로 쓰는 규칙을 뒤집지 마라
  — 이유: doc_ws_root 계약 (step 1)이 레이아웃 권위를 doc_loops 행에 둔다.
- `workspaces/` 아래 직접 쓰기 금지 (SSOT 가드훅) — fixture는 tmp_path·db_env.