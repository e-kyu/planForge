# -*- coding: utf-8 -*-
"""docloops 서비스 잠금 테스트 — 문서별 독립 진행 상태머신 (independent-doc-loops).

project 시드는 tests/_helpers.make_project (app/client fixture 경유) — step 3부터
create_project가 루프 3행을 시드한다(단일 생성 권위). "행 없는(레거시) 프로젝트"
시나리오는 시드 후 행을 지워 만든다 (`_legacy_project`). locked는 도달 불가 잔여
상태 — 잔존 데이터의 안전망 분기만 DB 직접 세팅으로 핀한다.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from _helpers import make_project, make_session
from app.modules.docloops.facade import (
    DOC_KINDS,
    DocLoop,
    DocLoopStatus,
    delete_project_data,
    doc_label,
    has_doc_layout,
    init_project_loops,
    list_loops,
    on_plan_approved,
    require_session_doc,
)
from app.modules.interview.facade import complete_plan_review_sessions
from app.modules.interview.infrastructure.models import (
    InterviewSession,
    SessionPhase,
    SessionStatus,
)
from app.shared.errors import CodedHTTPError


def _legacy_project(client, slug: str) -> int:
    """doc_loops 행이 없는 (레거시) 프로젝트 — 행의 단일 생성 권위는 create_project
    훅이므로, 레거시 시나리오는 시드된 행을 지워 시뮬레이션한다."""
    pid = make_project(client, slug)
    with make_session(client) as db:
        delete_project_data(db, pid)
        db.commit()
    return pid


def _status(client, pid: int, slug: str) -> DocLoopStatus:
    with make_session(client) as db:
        rows = {r.doc_slug: r.status for r in list_loops(db, pid)}
    return rows[slug]


def _statuses(client, pid: int) -> dict[str, DocLoopStatus]:
    with make_session(client) as db:
        return {r.doc_slug: r.status for r in list_loops(db, pid)}


def test_init_creates_three_rows_idempotent(client):
    pid = make_project(client, "docinit")
    with make_session(client) as db:
        init_project_loops(db, pid)
        db.commit()
    st = _statuses(client, pid)
    assert len(st) == 3
    assert st["proposal"] == DocLoopStatus.ACTIVE
    assert st["uiux-design"] == DocLoopStatus.ACTIVE
    assert st["dev-design"] == DocLoopStatus.ACTIVE
    # 재호출 — 멱등 (3행 유지, 상태 보존)
    with make_session(client) as db:
        init_project_loops(db, pid)
        db.commit()
    assert len(_statuses(client, pid)) == 3
    assert _status(client, pid, "proposal") == DocLoopStatus.ACTIVE


def test_on_plan_approved_own_doc_only(client):
    """승인 훅은 자기 문서 행만 done으로 전환하고 다른 문서 행은 절대 건드리지 않는다
    (독립 진행) — 역순 승인(개발설계서 먼저)에서도 나머지는 active로 유지된다."""
    pid = make_project(client, "docindep")
    with make_session(client) as db:
        init_project_loops(db, pid)
        db.commit()

    # 역순 승인 — dev-design 먼저
    with make_session(client) as db:
        on_plan_approved(db, pid, "dev-design")
        db.commit()
    st = _statuses(client, pid)
    assert st["dev-design"] == DocLoopStatus.DONE
    assert st["proposal"] == DocLoopStatus.ACTIVE
    assert st["uiux-design"] == DocLoopStatus.ACTIVE

    # proposal 승인 — 자기 행만 done, dev-design는 done 유지 (재잠금 없음)
    with make_session(client) as db:
        on_plan_approved(db, pid, "proposal")
        db.commit()
    st = _statuses(client, pid)
    assert st["proposal"] == DocLoopStatus.DONE
    assert st["uiux-design"] == DocLoopStatus.ACTIVE
    assert st["dev-design"] == DocLoopStatus.DONE

    # 재승인(세대 교체 시나리오) — 멱등 (다른 문서 행 불변)
    with make_session(client) as db:
        on_plan_approved(db, pid, "proposal")
        db.commit()
    st = _statuses(client, pid)
    assert len(st) == 3
    assert st["proposal"] == DocLoopStatus.DONE
    assert st["uiux-design"] == DocLoopStatus.ACTIVE
    assert st["dev-design"] == DocLoopStatus.DONE


def test_on_plan_approved_none_or_unknown_is_noop(client):
    pid = make_project(client, "docnoop")
    with make_session(client) as db:
        init_project_loops(db, pid)
        db.commit()
    before = _statuses(client, pid)

    with make_session(client) as db:
        on_plan_approved(db, pid, None)
        on_plan_approved(db, pid, "unknown-slug")
        db.commit()
    assert _statuses(client, pid) == before


def test_on_plan_approved_rows_missing_is_noop(client):
    """루프 행이 없는 (기존/레거시) 프로젝트에 영향 없음 — 그리고 이 시나리오에서
    has_doc_layout은 False로 남는다."""
    pid = _legacy_project(client, "doclegacy")
    with make_session(client) as db:
        on_plan_approved(db, pid, "proposal")
        db.commit()
    with make_session(client) as db:
        assert list_loops(db, pid) == []
        assert has_doc_layout(db, pid) is False


def test_require_session_doc(client):
    pid = make_project(client, "docgate")
    with make_session(client) as db:
        init_project_loops(db, pid)
        db.commit()

    # 미상 slug → http_404 계열
    with make_session(client) as db:
        with pytest.raises(CodedHTTPError) as ei:
            require_session_doc(db, pid, "nonsense")
        assert ei.value.status_code == 404

    # 3종 전부 active — 세션 생성 게이트는 모두 통과 (독립 진행)
    with make_session(client) as db:
        assert require_session_doc(db, pid, "proposal") == "proposal"
        assert require_session_doc(db, pid, "uiux-design") == "uiux-design"
        assert require_session_doc(db, pid, "dev-design") == "dev-design"

    # 승인 후 done — 재작업(세션 재생성) 허용
    with make_session(client) as db:
        on_plan_approved(db, pid, "proposal")
        db.commit()
    with make_session(client) as db:
        assert require_session_doc(db, pid, "proposal") == "proposal"

    # locked는 도달 불가 잔여 상태 — DB 직접 세팅해 안전망 409 분기를 핀한다
    with make_session(client) as db:
        row = db.scalars(
            select(DocLoop).where(
                DocLoop.project_id == pid, DocLoop.doc_slug == "uiux-design")).first()
        row.status = DocLoopStatus.LOCKED
        db.commit()
    with make_session(client) as db:
        with pytest.raises(CodedHTTPError) as ei:
            require_session_doc(db, pid, "uiux-design")
        assert ei.value.status_code == 409

    # 행 없는 (레거시) 프로젝트의 캐노니컬 slug → 통과
    legacy = _legacy_project(client, "docgatelegacy")
    with make_session(client) as db:
        assert require_session_doc(db, legacy, "dev-design") == "dev-design"
        assert has_doc_layout(db, legacy) is False


def test_list_loops_preserves_doc_kinds_order(client):
    pid = make_project(client, "docorder")
    with make_session(client) as db:
        init_project_loops(db, pid)
        db.commit()
    with make_session(client) as db:
        rows = list_loops(db, pid)
    assert [r.doc_slug for r in rows] == [slug for slug, _ in DOC_KINDS]


def test_has_doc_layout(client):
    pid = _legacy_project(client, "doclayout")
    with make_session(client) as db:
        assert has_doc_layout(db, pid) is False
        init_project_loops(db, pid)
        db.commit()
    with make_session(client) as db:
        assert has_doc_layout(db, pid) is True


def test_complete_plan_review_sessions_doc_scoped(client):
    """plan 승인 완료 처리의 문서 스코프 (step 4) — slug를 주면 그 문서 세션만 완료.

    step 5(문서 plan 승인)가 이 파라미터를 이어받고, None은 전체(기존 계약)다 —
    레거시 plan 승인 경로와 기존 테스트 계약이 None=전체에 고정돼 있다.
    """
    pid = make_project(client, "docsessscope")
    with make_session(client) as db:
        p = InterviewSession(project_id=pid, doc_slug="proposal",
                             phase=SessionPhase.PLAN_REVIEW)
        u = InterviewSession(project_id=pid, doc_slug="uiux-design",
                             phase=SessionPhase.PLAN_REVIEW)
        db.add_all([p, u])
        db.commit()
        p_id, u_id = p.id, u.id

    # 문서 스코프 — proposal 세션만 완료 (APPROVED/DONE), uiux 세션은 PLAN_REVIEW 유지
    with make_session(client) as db:
        complete_plan_review_sessions(db, pid, doc_slug="proposal")
        db.commit()
    with make_session(client) as db:
        rows = {s.id: s for s in db.scalars(
            select(InterviewSession).where(InterviewSession.project_id == pid)).all()}
        assert rows[p_id].phase == SessionPhase.APPROVED
        assert rows[p_id].status == SessionStatus.DONE
        assert rows[u_id].phase == SessionPhase.PLAN_REVIEW

    # None(기본) — 전체 기존 동작: 남은 uiux 세션도 완료한다
    with make_session(client) as db:
        complete_plan_review_sessions(db, pid)
        db.commit()
    with make_session(client) as db:
        for s in db.scalars(
                select(InterviewSession).where(InterviewSession.project_id == pid)):
            assert s.phase == SessionPhase.APPROVED and s.status == SessionStatus.DONE


def test_doc_label_bidirectional_mapping():
    for slug, label in DOC_KINDS:
        assert doc_label(slug) == label
    with pytest.raises(ValueError):
        doc_label("nonsense")


def test_delete_project_data_removes_all_rows(client):
    pid = make_project(client, "docdelete")
    with make_session(client) as db:
        init_project_loops(db, pid)
        db.commit()
    with make_session(client) as db:
        on_plan_approved(db, pid, "proposal")
        delete_project_data(db, pid)
        db.commit()
    with make_session(client) as db:
        assert list_loops(db, pid) == []
        assert has_doc_layout(db, pid) is False