# Step 2: docloops-facade

## 읽어야 할 파일

먼저 아래 파일들을 읽어라:

- `/CLAUDE.md` — 설계 원칙 계약 + 모듈 경계(타 모듈 테이블·내부 직접 import 금지,
  facade만 노출)
- `/docs/ARCHITECTURE.md` — 가이드 §1.2 모듈 템플릿 구조
- `/backend/app/modules/facts/facade.py` — 소형 모듈 facade 실례 (`__all__` 명시,
  함수 docstring에 커밋 계약 명기)
- `/backend/app/shared/errors.py` — `http_404`·`http_409` (facade에서 오류 검증 시
  이 헬퍼를 쓴다 — plans facade의 `require_plan` 패턴)
- `/backend/app/modules/docloops/infrastructure/models.py` — step 0 산출물 (DocLoop,
  DocLoopStatus)
- `/backend/app/shared/workspace.py` — step 1 산출물 (doc_ws_root·ensure_doc_ws —
  이 step에서는 수정 없음, 의미만 파악)
- `/tests/conftest.py` — db fixture 구조

step 0·1 산출물(`phases/doc-loop/step0-output.json`, `step1-output.json`)의 summary도
읽고 진행하라.

## 작업

`backend/app/modules/docloops/`의 application 계층(serivce)과 facade를 구현한다.
이 step에서는 API 라우터·타 모듈 수정을 하지 않는다.

기능 배경: 문서 루프 상태머신은 단방향 래치다 —

```
locked ──(이전 문서 plan 승인됨)──▶ active ──(이 문서의 plan 승인됨)──▶ done
```

- 문서 캐노니컬 매핑(생성 순서 = 활성화 순서): `proposal` > `uiux-design` >
  `dev-design`. 사용자 어휘는 제안서·UI·UX설계서·개발설계서 (한글 어휘는 plan 본문
  `- 산출 문서:` 라인·슬라이드 태그에 쓰인다 — 이 모듈은 slug만 다룬다).
- 래치: 잠금 해제는 되돌리지 않는다. 이전 문서를 재수정·재승인해도 done은 done이고,
  이미 active 이상인 다음 문서를 다시 잠그지 않는다. done 문서는 세션 재생성(재작업)을
  허용하고, locked만 세션 생성을 막는다.
- plan 진행상황(plan_version 등)은 루프 행에 저장하지 않는다 — plans 행 역참조가
  SSOT이며 이 step은 그 데이터를 다루지 않는다(step 3에서 한다).

### 1. `backend/app/modules/docloops/application/service.py`

핵심 상수와 함수 시그니처:

```python
# slug(디렉터리·계약 식별자)와 한글 라벨의 SSOT — 생성 순서로 정렬
DOC_KINDS: tuple[tuple[str, str], ...] = (
    ("proposal", "제안서"),
    ("uiux-design", "UI·UX설계서"),
    ("dev-design", "개발설계서"),
)

def doc_label(doc_slug: str) -> str: ...
    # 미상 slug → ValueError

def init_project_loops(db: Session, project_id: int) -> None: ...
    # 3행 생성: proposal=active, uiux-design=locked, dev-design=locked.
    # 커밋은 호출자 트랜잭션에서 (flush로 채번만 — facts.facade 패턴).
    # 호출 전 이미 행이 있으면 만들지 않는다(멱등).

def list_loops(db: Session, project_id: int) -> list[DocLoop]: ...
    # DOC_KINDS 순서로 정렬해 반환 (매핑에 없는 slug는 뒤로)

def has_doc_layout(db: Session, project_id: int) -> bool: ...
    # 행이 1개라도 있으면 True — 문서별 경로 사용 여부의 권위 (limit(1) 쿼리)

def require_session_doc(db: Session, project_id: int, doc_slug: str) -> str: ...
    # DOC_KINDS에 없는 slug → http_404
    # 행이 없으면(레거시 프로젝트) slug를 그대로 반환 — 캐노니컬 slug 검증만 통과
    # 행의 status가 locked → http_409 ("이전 문서의 plan 승인 후 ... 활성화" 안내)
    # active/done → slug 반환 (done도 재작업 허용)

def on_plan_approved(db: Session, project_id: int, doc_slug: str | None) -> None: ...
    # doc_slug가 None이거나 DOC_KINDS에 없으면 no-op (레거시 plan 승인)
    # 자기 문서 행을 done으로 전환(멱등 — 이미 done이어도 유지)
    # DOC_KINDS 순서상 바로 다음 문서 행이 locked면 active로 (래치 — active/done 건드림 금지)
    # 행이 아예 없으면 no-op (기존 프로젝트에 영향 없음)

def delete_project_data(db: Session, project_id: int) -> None: ...
    # 해당 프로젝트의 DocLoop 행 전체 delete
```

모듈 경계 계약(핵심): docloops는 리프 모듈이다. **다른 모듈의 facade를 절대 import
하지 않는다** — plan 승인 훅·세션 게이트는 plans·interview 쪽이 이 facade를 호출하는
방향이며, docloops는 받은 값만 다룬다. import는 `app.shared`(errors 포함)와 자기 모듈
내부만 가능하다.

### 2. `backend/app/modules/docloops/facade.py`

facts 모듈 패턴을 따른다 — service의 공개 함수를 재수출하고:

```python
__all__ = [
    "DocLoopStatus", "DocLoop", "DOC_KINDS", "doc_label",
    "init_project_loops", "list_loops", "require_session_doc",
    "on_plan_approved", "has_doc_layout", "delete_project_data",
]
```

### 3. 신규 테스트 `tests/test_docloops_service.py`

conftest의 db fixture를 사용하고, project 생성은 `tests/_helpers.make_project` 또는
app 생성 없이 직접 DB seeding이 가능하면 그것을 쓴다 (conftest 구조를 먼저 확인).
케이스:

- `init_project_loops` → 행 3개, proposal만 active, 나머지 locked. 재호출 시 3행 유지
- `on_plan_approved(db, pid, "proposal")` → proposal done, uiux-design active,
  dev-design locked. `on_plan_approved(db, pid, "uiux-design")` → dev-design active
- 래치: 이후 `on_plan_approved(db, pid, "proposal")` 재호출(재승인 시나리오) →
  uiux-design·dev-design가 여전히 active·active이고 행은 3개 유지
- `on_plan_approved(db, pid, None)` → 어떤 행도 변하지 않음
- `require_session_doc`: 미상 slug → `app.shared.errors` 계열 예외; 행 없는 프로젝트의
  캐노니컬 slug → 통과; locked → 409 계열 예외; active·done → 통과
- `list_loops` 정렬 순서가 DOC_KINDS와 동일
- `has_doc_layout` True/False
- `doc_label`의 양방향 매핑 (label→slug 역함수는 만들지 않는다 — 필요 없다)

## Acceptance Criteria

```bash
python -m pytest tests/test_docloops_service.py -q   # 저장소 루트에서
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트:
   - docloops 모듈이 타 모듈(`plans`·`interview`·`projects` 등)의 파일을 import하지
     않는가? (grep으로 직접 확인)
   - `DocLoop` 행은 이 모듈 facade 경유로만 다루는가? (presentation·타 모듈 직접 접근 없음)
3. 결과에 따라 `/phases/doc-loop/index.json`의 해당 step을 업데이트한다
   (성공 → `"status": "completed"` + `"summary"` — 다음 step이 facade 함수 목록을
   컨텍스트로 받을 수 있게 산출 파일 경로를 함께 적는다).

## 금지사항

- 타 모듈 facade import 금지 — 이유: 이 기능의 의존성 방향 설계는 projects/plans/interview
  → docloops다. docloops가 plans를 import하면 승인 훅에서 순환 참조가 생긴다.
- 루프 행에 plan_id·plan_version 같은 plan 캐시 컬럼/필드를 두는 것 금지 — 이유:
  plan 진행상황의 SSOT은 plans 행이다 (step 3에서 역참조 쿼리로 해결).
- `on_plan_approved`에서 active→locked 역전이 금지 — 이유: 단방향 래치가 요구사항이고,
  재승인(세대 교체)마다 다음 문서가 재잠기면 선순환이 되지 않는다. 재잠금은 (미확정)으로
  기록돼 있고 이 기능의 확정 범위 아니다.
- `http_404`·`http_409` 대신 임의 예외를 정의해 던지는 것 금지 — 이유: FastAPI 전역
  오류 매핑(shared/errors.py)을 통과해야 계약 응답 형식이 유지된다.
- API 라우터·타 모듈 수정 금지 — 이유: scope 최소화. API 표면은 step 3이다.