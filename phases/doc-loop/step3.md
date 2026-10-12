# Step 3: docloops-api-projects

## 읽어야 할 파일

먼저 아래 파일들을 읽어라:

- `/CLAUDE.md` — 설계 원칙 계약 (모듈 경계: facade 경유) + 계약 우선
- `/docs/ARCHITECTURE.md` — 라우터 조립·OpenAPI 계약 흐름
- `/backend/app/modules/docloops/facade.py` + `application/service.py` — step 2 산출물
  (DOC_KINDS, init_project_loops, list_loops, require_session_doc, on_plan_approved,
  has_doc_layout, delete_project_data, doc_label, DocLoopStatus, DocLoop)
- `/backend/app/modules/plans/facade.py` — `create_generation`·`latest_approved`·
  `next_version_no` 현재 시그니처
- `/backend/app/modules/plans/presentation/api.py` + `presentation/schemas.py` —
  `list_plans`·`PlanOut` (이 step에서 doc_slug 파라미터만 확장한다)
- `/backend/app/modules/projects/application/service.py` + `presentation/api.py` +
  `presentation/schemas.py` — create/delete 오케스트레이션·`ProjectOut`
- `/backend/app/api.py` — 라우터 조립
- `/backend/app/modules/jobs/presentation/schemas.py` 참조 사례 — plans presentation api가
  타 모듈 presentation 스키마(`JobOut`)를 import한 선례가 있다 (module 경계상 facade 다음으로
  허용되는 공개 계약 표면)
- `/tests/test_projects_api.py` + `/tests/_helpers.py` + `/tests/conftest.py`

step 2까지의 산출물은 `phases/doc-loop/step{0,1,2}-output.json`의 summary로 확인하라.

## 작업

이 step에서 문서 루프의 "읽기 API 표면"과 프로젝트 라이프사이클 통합을 한다.
쓰게 되는 코드는 상태 변경 로직(init/delete 훅)뿐이고, plan 승인 훅은 step 5다.

기능 배경: 프론트 프로젝트 카드는 3개 문서 버튼의 상태(locked/active/done)를
**프로젝트 목록 1개 호출 안에서** 알아야 한다 (N+1 없이). 그래서 `ProjectOut`에
docloops 상태를 내장한다. 문서별 plan 진행 버전은 plans 행의 역참조 파생값이다
(루프 행에 캐시하지 않는다 — SSOT).

### 1. plans facade 확장 (읽기·채번 파라미터 — 기존 계약 유지)

`backend/app/modules/plans/facade.py`:

```python
def latest_generations_by_doc(db: Session, project_id: int) -> dict[str | None, Plan]:
    """문서별(없음 None 포함) 최신 plan 세대. 상태 무관 최신(version_no desc) —
    한 번의 쿼리를 version_no desc 순으로 훑고 키별 최신만 남긴다."""

def latest_approved(db: Session, project_id: int, doc_slug: str | None = None) -> Plan | None:
    # 기존 동작 유지 + doc_slug가 주어지면 그 문서로 좁힌다 (None = 문서 무관, 기존 계약)

def create_generation(db, project_id, *, markdown, docs=None, parsed_ok=False,
                      status=PlanStatus.DRAFT, origin, doc_slug: str | None = None) -> Plan:
    # doc_slug 파라미터만 추가(기본 None). version_no는 프로젝트 전체 단조 유지
    # (uq_project_planver — 문서별 재채번 금지, 무손실 채번 계약).
```

`Plan` 모델(`plans/infrastructure/models.py`)에 `doc_slug` nullable String(32) 컬럼과
`PlanOut`(`plans/presentation/schemas.py`)에 `doc_slug: str | None`을 추가한다.

`plans/presentation/api.py list_plans`에 선택적 `doc_slug: str | None = Query(default=None)`
을 추가 — 주어지면 `Plan.doc_slug == doc_slug` 필터, None이면 전체(기존 동작).

### 2. docloops presentation — 상태 API

`backend/app/modules/docloops/presentation/{schemas.py, api.py}`:

```python
class DocLoopOut(BaseModel):
    doc_slug: str
    label: str          # doc_label(doc_slug) — 제안서 | UI·UX설계서 | 개발설계서
    status: str         # locked | active | done
    plan_version: int | None = None   # 최신 plan 세대 version_no (역참조 파생)
    plan_id: int | None = None

# GET /api/projects/{project_id}/docloops -> list[DocLoopOut]
#   require_project → 404. list_loops(DB 행 순서는 DOC_KINDS 정렬) + latest_generations
#   + _by_doc를 조합해 채운다. doc_loops 행이 없는 프로젝트(레거시)는 []를 반환한다 —
#   프론트는 빈 목록을 "레거시 프로젝트"로 보고 문서 버튼을 렌더링하지 않는다.
```

라우터는 `APIRouter(tags=["docloops"])` + 전체 경로 스타일(plans 라우터 패턴)으로 만들고
`app/api.py`의 `api_router.include_router(...)` 목록 끝에 추가한다.

### 3. 프로젝트 라이프사이클 통합

`backend/app/modules/projects/application/service.py`:

- `create_project`: `create_workspace`·Project flush 이후 **같은 트랜잭션**에서
  `docloops.facade.init_project_loops(db, p.id)` 호출 (projects → docloops 방향 —
  경배 계약 준수). import는 `app.modules.docloops import facade as docloops` 스타일.
- `delete_project`: 자식 → 부모 삭제 사슬에 `docloops.facade.delete_project_data(db,
  project_id)`를 추가한다 (다른 delete_*와 같은 위치 — doc_loops가 jobs 행보다 먼저
  지워질 필요는 없으나 사슬 안에만 있으면 된다).

`projects/presentation/schemas.py` — `ProjectOut`에 내장:

```python
from app.modules.docloops.presentation.schemas import DocLoopOut

class ProjectOut(BaseModel):
    ...
    docloops: list[DocLoopOut] = []
```

`projects/presentation/api.py`:

- `_project_out(p, db)` 형태로 확장해 각 응답에 docloops를 채운다.
- 목록(`list_projects`)은 **배치 로드**로 N+1 방지: 프로젝트 id 목록 →
  `select(DocLoop).where(project_id.in_(ids))` 1회 + plans 최신 세대도 1회
  (`select(Plan).where(project_id.in_(ids))`를 version_no desc로 훑어
  (project, doc_slug)별 최신만 파이썬에서 채택) → id별로 DocLoopOut 조립.
- 단건(`get_project`·`create_project`·`update_project`) 응답에도 동일 데이터 채움.
- 타 모듈 테이블을 직접 import하지 않는다 — `docloops.facade`의 `DocLoop` 재수출과
  `plans.facade` 경유를 사용한다. (facade가 재수출한 모델 클래스를
  presentation에서 쓰는 것은 jobs 패턴 선례 범위다.)

### 4. 신규 테스트 `tests/test_docloops_api.py` (파트 1)

conftest와 `tests/_helpers.py`를 따른다:

- 프로젝트 생성 201 → `GET /api/projects/{id}/docloops` = 3건, 순서
  proposal(active) > uiux-design(locked) > dev-design(locked), label 매핑 검증,
  plan_version은 모두 null
- `GET /api/projects`(목록) 응답의 각 항목이 docloops 3건을 가진다
- 프로젝트 상세 단건에도 docloops 포함
- DB에서 doc_loops 행을 모두 delete한 시드 프로젝트 → docloops = [] (레거시 계약)
- 프로젝트 삭제 후 doc_loops 행도 사라짐 (`test_projects_api.py`의 삭제 캐스케이드
  케이스 스타일로 해당 파일에 케이스 추가해도 좋다)

## Acceptance Criteria

```bash
python -m pytest tests/test_docloops_api.py tests/test_projects_api.py tests/test_plans_api.py -q   # 저장소 루트에서
```

기존 `test_projects_api`·`test_plans_api`가 무수정 통과해야 한다 (facade 파라미터는
기본값 None이라 기존 호출자 영향 없음).

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트:
   - projects/plans/docloops 간 접근이 전부 facade(`docloops.facade`·`plans.facade`)
     경유인가? (타 모듈 infrastructure 직접 import 금지)
   - `create_generation`·`latest_approved`의 기존 호출자들이 무수정으로 남는가?
   - version_no 채번이 프로젝트 전체 단조인가? (문서별 재시작 금지)
3. 결과에 따라 `/phases/doc-loop/index.json`의 해당 step을 업데이트한다
   (completed + summary — 다음 step에서 plans facade 확장 상태를 이어받을 수 있게 기술).

## 금지사항

- `ProjectOut`을 선택적 필드 없이 하드 리쿼일드하는 것 — `docloops: list[DocLoopOut] = []`
  기본값으로 기존 클라이언트(생성된 TS 타입 갱신 전) 호환을 유지해야 한다.
- 프로젝트 목록에서 프로젝트별 plans 쿼리를 단건 반복(N+1)하는 것 금지 — 이유:
  목록 화면이 매번 이 응답을 그대로 사용하며, 배치 쿼리 설계 의도는 위에 명시했다.
- `approve_plan` 등 plan 상태 변경 로직 수정 금지 — 이유: 승인 훅·supersede 좁힘은
  step 5의 scope다. 이 step에서 plans는 facade 파라미터·읽기 헬퍼까지만.
- doc_loops 행을 프로젝트 생성 외 경로에서 임의 생성하는 유틸 추가 금지 — 이유:
  init은 `create_project`가 단일 권위다.
- `workspaces/` 아래 직접 쓰기 금지 (SSOT 가드훅)