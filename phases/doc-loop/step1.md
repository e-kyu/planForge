# Step 1: workspace-doc-root

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 규약을 파악하라:

- `/CLAUDE.md` — 설계 원칙 계약 (원칙 5 무손실 채번 — output/ 규약 연관)
- `/backend/app/shared/workspace.py` — 전체. `WORKSPACE_SUBDIRS`(20행),
  `validate_slug`·`SLUG_RE`(27행), `create_workspace`, `ensure_workspace_dirs`,
  `write_plan_mirror`(58행), `atomic_build`(261행)를 확인한다
- `/tests/test_projects_api.py` — 워크스페이스 레이아웃을 핀(pinning)하는 기존 계약
  (프로젝트 생성 시 루트 5개 subdir 검증)
- `/tests/conftest.py` — 테스트 환경

step 0(`phases/doc-loop/step0.md` 완료물)에서 `doc_loops` 테이블과
`app/modules/docloops/infrastructure/models.py`(DocLoop, DocLoopStatus)가 생성됐다.
파일을 읽고 `doc_slug` 값의 도메인(proposal/uiux-design/dev-design)을 파악한 뒤 작업하라.

## 작업

`backend/app/shared/workspace.py`에 문서별 루프 워크스페이스 경로 헬퍼 3개를 추가한다.
기존 함수·상수는 **한 글자도 변경하지 않는다**.

기능 배경: 각 문서 루프는 `workspaces/{프로젝트slug}/{문서slug}/` 하위에
work·output·docs·assets를 가진다. `sources/`는 문서 간 공유 소스이므로 프로젝트
루트에 남는다 (문서별 하위에 만들지 않는다). 레이아웃의 권위는 디렉토리 존재 여부가
아니라 **DB 행(doc_loops)의 존재**다 — 행이 있는(신규) 프로젝트만 문서별 경로를 쓰고,
행이 없는 기존 프로젝트는 마이그레이션 없이 루트 경로로 계속 동작한다.

1. 상수 추가:

```python
# 문서별 루프 워크스페이스 하위 구조 — sources는 문서 간 공유라 루트에 남는다
DOC_WS_SUBDIRS = ("work", "output", "docs", "assets")
```

2. 루트 결정 헬퍼 — 시그니처 고정:

```python
def doc_ws_root(ws: Path, doc_slug: str | None, *, doc_layout: bool) -> Path:
    """문서별 ws 루트 — doc_layout(=프로젝트가 doc_loops 행을 가짐)이고 doc_slug가
    있으면 ws/{doc_slug}, 그 외(레거시 · doc 없는 plan)는 ws를 반환한다."""
```

구현 규칙:
- `doc_slug and doc_layout`일 때만 하위 경로를 반환하며, 그 경우
  `validate_slug(doc_slug)`로 경로 성분을 검증한 뒤 반환한다 (잘못된 slug가
  트래버설이 되지 않게 — `..` 등은 WorkspaceError).
- 나머지는 전부 `ws`를 그대로 반환한다 (doc_layout=False + doc_slug="proposal"
  조합도 ws 루트 — 레거시 프로젝트의 문서 세션 허용 계약).
- 판정은 절대 디렉토리 존재 시행으로 하지 않는다 (`is_dir()` 확인 금지) —
  DB 행이 권위이고, 존재 확인은 race·지연 생성과 충돌한다.

3. 지연 생성 헬퍼:

```python
def ensure_doc_ws(root: Path) -> Path:
    """문서별 루프가 시작될 때(세션 생성 시점) 하위 구조를 지연 생성한다."""
```

- `DOC_WS_SUBDIRS`를 `mkdir(parents=True, exist_ok=True)`로 만들고 root를 반환한다
  (`ensure_workspace_dirs`와 동일 스타일).
- `create_workspace`처럼 기존 디렉토리를 오류로 취급하지 않는다 — 멱등해야 한다.

4. 신규 테스트 `tests/test_workspace_doc_root.py` (tmp_path 기반):
- doc_layout=True + "proposal" → `ws/proposal` 반환
- doc_layout=False + "proposal" → `ws` 반환
- doc_slug=None (doc_layout=True) → `ws` 반환
- ensure_doc_ws가 4개 subdir(work·output·docs·assets)를 생성하고, 재호출 시
  멱등하며, 기존 파일을 훼손하지 않는지 단언
- doc_layout=True + ".." 같은 SLUG_RE 위반 slug → WorkspaceError 단언

## Acceptance Criteria

```bash
python -m pytest tests/test_workspace_doc_root.py tests/test_projects_api.py -q   # 저장소 루트에서
```

기존 `test_projects_api`(루트 5 subdir 핀 테스트 포함)가 무수정 통과해야 한다.

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트:
   - 기존 워크스페이스 함수(`create_workspace`·`atomic_build`·`write_plan_mirror` 등)의
     시그니처·동작을 변경하지 않았는가?
   - 이 step은 `app/shared/workspace.py`와 신규 테스트만 다루는가? (모듈 파일 수정 없음)
3. 결과에 따라 `/phases/doc-loop/index.json`의 해당 step을 업데이트한다
   (성공 → `"status": "completed"` + `"summary"`).

## 금지사항

- `WORKSPACE_SUBDIRS`·`create_workspace`·`ensure_workspace_dirs`에 문서별 개념을 녹이는
  것 금지 — 이유: 루트 5 subdir는 기존 계약이고 문서별 하위는 `DOC_WS_SUBDIRS`가 별도
  관리한다. `sources`가 `DOC_WS_SUBDIRS`에 포함되면 문서 간 공유 소스 계약이 깨진다.
- `doc_ws_root`에서 디렉토리 존재 여부로 판정 금지 — 이유: 레이아웃 권위는 DB 행이며
  존재 확인은 지연 생성·race와 충돌한다.
- `validate_slug` 로직 변경 금지 — 이유: 문서 slug도 프로젝트 slug와 동일 규약
  (ASCII 소문자/숫자/하이픈)으로 고정되어 있다.
- `workspaces/` 아래 직접 쓰기 금지 — 이유: SSOT 가드훅이 차단한다. fixture는 tmp_path를 쓴다.
- 기존 테스트를 깨뜨리지 마라.