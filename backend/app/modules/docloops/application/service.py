# -*- coding: utf-8 -*-
"""docloops 애플리케이션 서비스 — 문서별 선순환 루프 상태머신.

단방향 래치: locked ──(이전 문서 plan 승인)──▶ active ──(이 문서 plan 승인)──▶ done.
잠금 해제는 되돌리지 않는다 — 이전 문서를 재수정·재승인해도 done은 done이고,
이미 active 이상인 다음 문서를 다시 잠그지 않는다. done 문서는 세션 재생성(재작업)을
허용하고, locked만 세션 생성을 막는다.

모듈 경계: docloops는 리프 모듈이다 — 타 모듈의 facade를 import하지 않는다.
plan 승인 훅·세션 게이트는 plans·interview 쪽이 이 모듈의 facade를 호출하는 방향이며,
docloops는 받은 값만 다룬다. 커밋은 호출자 트랜잭션에서 (facts.facade 패턴 — flush만).
"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.shared.errors import http_404, http_409

from ..infrastructure.models import DocLoop, DocLoopStatus

# slug(디렉터리·계약 식별자)와 한글 라벨의 SSOT — 생성 순서 = 활성화 순서.
# 한글 어휘는 plan 본문 `- 산출 문서:` 라인·슬라이드 태그에 쓰이고, 이 모듈은 slug만 다룬다.
DOC_KINDS: tuple[tuple[str, str], ...] = (
    ("proposal", "제안서"),
    ("uiux-design", "UI·UX설계서"),
    ("dev-design", "개발설계서"),
)

_SLUG_ORDER = {slug: i for i, (slug, _) in enumerate(DOC_KINDS)}


def doc_label(doc_slug: str) -> str:
    """slug → 한글 라벨. 미상 slug는 ValueError (호출자 버그 조기 노출)."""
    for slug, label in DOC_KINDS:
        if slug == doc_slug:
            return label
    raise ValueError(f"알 수 없는 문서 slug입니다: {doc_slug!r}")


def _rows_by_slug(db: Session, project_id: int) -> dict[str, DocLoop]:
    return {r.doc_slug: r for r in db.scalars(
        select(DocLoop).where(DocLoop.project_id == project_id))}


def init_project_loops(db: Session, project_id: int) -> None:
    """프로젝트 생성 시 루프 3행을 시드한다: proposal=active, 나머지 locked.

    멱등 — 이미 행이 있는 slug는 다시 만들지 않는다. 커밋은 호출자 트랜잭션에서
    (flush로 채번만 — facts.facade 패턴).
    """
    existing = _rows_by_slug(db, project_id)
    for slug, _label in DOC_KINDS:
        if slug in existing:
            continue
        status = DocLoopStatus.ACTIVE if slug == DOC_KINDS[0][0] else DocLoopStatus.LOCKED
        db.add(DocLoop(project_id=project_id, doc_slug=slug, status=status))
    db.flush()


def list_loops(db: Session, project_id: int) -> list[DocLoop]:
    """루프 행 전체 — DOC_KINDS 순서로 정렬 (매핑에 없는 slug는 뒤로)."""
    rows = db.scalars(select(DocLoop).where(DocLoop.project_id == project_id)).all()
    return sorted(rows, key=lambda r: (_SLUG_ORDER.get(r.doc_slug, len(DOC_KINDS)),
                                       r.doc_slug))


def has_doc_layout(db: Session, project_id: int) -> bool:
    """문서별 경로 사용 여부의 권위 — 행이 1개라도 있으면 True (레거시 프로젝트는 False)."""
    return db.scalars(
        select(DocLoop.id).where(DocLoop.project_id == project_id).limit(1)
    ).first() is not None


def require_session_doc(db: Session, project_id: int, doc_slug: str) -> str:
    """세션 생성 게이트 — 통과하면 doc_slug를 그대로 반환한다.

    - DOC_KINDS에 없는 slug → 404 (캐노니컬 slug만 허용).
    - 행이 없으면(레거시 프로젝트) slug를 그대로 반환 — 캐노니컬 slug 검증만 통과.
    - 행의 status가 locked → 409 ("이전 문서의 plan 승인 후 ... 활성화" 안내).
    - active/done → slug 반환 (done도 세션 재생성·재작업 허용).
    """
    if doc_slug not in _SLUG_ORDER:
        raise http_404(f"알 수 없는 문서 slug입니다: {doc_slug}")
    row = db.scalars(select(DocLoop).where(
        DocLoop.project_id == project_id, DocLoop.doc_slug == doc_slug)).first()
    if row is None:
        return doc_slug  # 레거시 프로젝트 — doc_loops 행 없이 루트 경로로 동작
    if row.status == DocLoopStatus.LOCKED:
        raise http_409(
            f"{doc_label(doc_slug)}은 아직 잠겨 있습니다 — "
            "이전 문서의 plan 승인 후 활성화됩니다")
    return doc_slug


def on_plan_approved(db: Session, project_id: int, doc_slug: str | None) -> None:
    """plan 승인 훅 (plans 모듈이 호출) — 자기 문서 done + 다음 문서 활성화 (래치).

    - doc_slug가 None이거나 DOC_KINDS에 없으면 no-op (레거시 plan 승인).
    - 자기 문서 행을 done으로 전환(멱등 — 이미 done이어도 유지).
    - DOC_KINDS 순서상 바로 다음 문서 행이 locked면 active로 (래치 — active/done은
      건드리지 않는다: 재잠금 없음).
    - 행이 아예 없으면 no-op (기존 프로젝트에 영향 없음).
    """
    if doc_slug is None or doc_slug not in _SLUG_ORDER:
        return
    rows = _rows_by_slug(db, project_id)
    if not rows:
        return
    own = rows.get(doc_slug)
    if own is not None:
        own.status = DocLoopStatus.DONE  # 멱등 — 재승인(세대 교체)에도 done 유지
    idx = _SLUG_ORDER[doc_slug]
    if idx + 1 < len(DOC_KINDS):
        nxt = rows.get(DOC_KINDS[idx + 1][0])
        if nxt is not None and nxt.status == DocLoopStatus.LOCKED:
            nxt.status = DocLoopStatus.ACTIVE  # 잠금 해제 래치 — 역전 금지
    db.flush()


def delete_project_data(db: Session, project_id: int) -> None:
    """프로젝트 삭제 사슬(projects 모듈이 호출) — 루프 행 전체 물리 삭제."""
    db.execute(delete(DocLoop).where(DocLoop.project_id == project_id))