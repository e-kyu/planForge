# Step 0: doc-loop-schema

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/CLAUDE.md` — 설계 원칙 계약 8개 (특히 원칙 1 SSOT·원칙 5 무손실 채번)
- `/docs/ARCHITECTURE.md` — 모듈 경계 규칙·모듈 템플릿 구조
- `/docs/ADR.md` — 기존 결정·편차 스타일 (이번 기능은 step 10에서 기록된다 — 지금은 참고만)
- `/backend/app/shared/types.py` — `StrEnum`, `_enum()` (native_enum=False), `UTCDateTime`, `UpdatedAtMixin`
- `/backend/app/modules/facts/infrastructure/models.py` — 신규 모듈 models 템플릿의 실례
- `/backend/app/modules/plans/infrastructure/models.py` — `uq_project_planver` 제약 확인
- `/backend/app/modules/derivatives/infrastructure/models.py` — `builds` 테이블 정의
- `/backend/alembic/versions/9c1f4e7b8a20_add_pending_round_summary.py` — nullable
  ADD COLUMN의 SQLite 선례
- `/backend/alembic/versions/c7e8d4a2f19b_add_updated_at.py` — batch_alter_table
  DROP COLUMN 선례
- `/tests/test_alembic_upgrade.py` — AC 대상
- `/backend/app/modules/__init__.py` — metadata 집계 (import 목록)

## 작업

"카드별 산출물 선순환 루프" Phase 1 — 문서별 루프 상태의 DB 스키마·모델만 확립한다.
이 step에서는 비즈니스 로직(service·API)을 만들지 않는다.

기능 배경 (자기완결 설명): 프로젝트 카드에 문서 버튼 3종(제안서 > UI·UX설계서 >
개발설계서)이 있고, 각 버튼이 자체 파이프라인 루프(인터뷰→팩트→plan 승인→derive/build)를
가진다. 이전 문서의 plan 승인(Approve)이 다음 문서 버튼의 활성화 조건이며, 각 문서는
`workspaces/{slug}/{문서슬러그}/` 하위에 자체 work·output·docs·assets를 둔다.
문서 정체성은 영문 슬러그로 저장한다: `proposal`·`uiux-design`·`dev-design`.
기존 프로젝트는 이관 대상이 아니므로 모든 doc_slug는 nullable이고 NULL = 레거시
(문서 루프 도입 전 · 워크스페이스 루트 경로).

### 1. Alembic 리비전 생성

`backend/alembic/versions/<revision_id>_add_doc_loops.py` — `down_revision = '9c1f4e7b8a20'`
(현재 head). revision id는 규격 내 임의 hex 문자열 사용 가능.

upgrade:

1. 신규 테이블 `doc_loops`:
   - `id` Integer PK
   - `project_id` Integer, FK `projects.id`, nullable=False, index=True
   - `doc_slug` String(32), nullable=False
   - `status` String(16), nullable=False, server_default='locked'
   - `created_at` DateTime, server_default=func.now()
   - `updated_at` DateTime nullable (다른 테이블과 동일 — updated_at는 UpdatedAtMixin
     상이하나 이 테이블은 append 후 갱신되므로 컬럼은 있어야 한다)
   - `UniqueConstraint('project_id', 'doc_slug', name='uq_project_docloop')`
2. ALTER TABLE (전부 nullable — SQLite ADD COLUMN 제약 회피):
   - `plans.doc_slug` String(32) nullable
   - `interview_sessions.doc_slug` String(32) nullable
   - `builds.doc_slug` String(32) nullable

upgrade/downgrade는 기존 리비전 선례 패턴(9c1f4e7b8a20·c7e8d4a2f19b)을 따른다.
downgrade에서 DROP COLUMN은 `op.batch_alter_table` 재작성으로 수행하고, doc_loops는
`op.drop_table`한다. **데이터 마이그레이션을 넣지 마라** — NULL = 레거시가 설계 의도다.

### 2. docloops 모듈 스켈레톤

`backend/app/modules/docloops/` 신규 생성 (모듈 템플릿 복제 규칙):

- `__init__.py` — facts 모듈 패턴: docstring + `from .infrastructure import models  # noqa: F401`
- `infrastructure/models.py`:

```python
class DocLoopStatus(StrEnum):
    LOCKED = "locked"      # 이전 문서 plan 승인 전 — 세션 생성 409
    ACTIVE = "active"      # 버튼 활성 — 세션 생성 가능
    DONE = "done"          # 자기 plan 승인 완료 — 재작업(세션 재생성) 가능

class DocLoop(UpdatedAtMixin, Base):
    __tablename__ = "doc_loops"
    __table_args__ = (UniqueConstraint("project_id", "doc_slug", name="uq_project_docloop"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    doc_slug: Mapped[str] = mapped_column(String(32))
    status: Mapped[DocLoopStatus] = mapped_column(
        _enum(DocLoopStatus), default=DocLoopStatus.LOCKED, server_default="locked"
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
```

`app/modules/__init__.py`의 `from . import (...)` 목록에 `docloops`를 알파벳순으로 추가한다
— alembic env.py와 init_db가 이 집계로 metadata를 채우므로 누락 시 테스트 DB에 테이블이
생성되지 않는다.

## Acceptance Criteria

```bash
python -m pytest tests/test_alembic_upgrade.py -q   # 저장소 루트에서
```

기존 테스트 전부 통과 + 신규 리비전이 upgrade/downgrade/재upgrade를 통과해야 한다.

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트:
   - docloops 모듈이 이번 step에서 타 모듈 파일을 import하지 않는가? (models는
     `app.shared`만 사용)
   - `doc_slug`에 SQLite 네이티브 ENUM을 쓰지 않았는가? (`_enum(StrEnum)` String 저장 필수)
3. 결과에 따라 `/phases/doc-loop/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary"`에 생성 파일 경로 포함해서 기록
   - 3회 실패 → `"status": "error"`, `"error_message"` 기록
   - 개입 필요 → `"status": "blocked"`, `"blocked_reason"` 기록 후 중단

## 금지사항

- `plans`·`interview_sessions`·`builds`의 기존 컬럼 수정·제약 추가 금지 — 이유: NULL=
  레거시 호환이 설계 의도이고, `uq_project_planver` 등 기존 제약은 채번 권위 계약이다.
- `doc_loops`에 plan_id·plan_version 등 파생 상태 컬럼 추가 금지 — 이유: plan 진행상황은
  plans 행 역참조가 SSOT이고, 루프에 캐시하면 이중 원본이 된다 (step 2의 facade 계약).
- Python 모델과 alembic 리비전의 컬럼 정의를 다르게 둬서는 안 된다 — 이유:
  `tests/test_alembic_upgrade.py`가 실제 upgrade로 검증하며 불일치는 후속 step 전부를 오염시킨다.
- fixture는 `tmp_path`·`tests/fixtures/`에 만들고 `workspaces/` 아래 쓰기 금지 — 이유:
  SSOT 가드훅(`.claude/hooks/guard_ssot.py`)이 차단한다.