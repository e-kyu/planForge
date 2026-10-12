# -*- coding: utf-8 -*-
"""docloops 서비스 잠금 테스트 — 문서 루프 단방향 래치 상태머신.

project 시드는 tests/_helpers.make_project (app/client fixture 경유) — step 3부터
create_project가 루프 3행을 시드한다(단일 생성 권위). "행 없는(레거시) 프로젝트"
시나리오는 시드 후 행을 지워 만든다 (`_legacy_project`).
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from _helpers import make_project, make_session
from app.modules.docloops.facade import (
    DOC_KINDS,
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
    assert st["uiux-design"] == DocLoopStatus.LOCKED
    assert st["dev-design"] == DocLoopStatus.LOCKED
    # 재호출 — 멱등 (3행 유지, 상태 보존)
    with make_session(client) as db:
        init_project_loops(db, pid)
        db.commit()
    assert len(_statuses(client, pid)) == 3
    assert _status(client, pid, "proposal") == DocLoopStatus.ACTIVE


def test_on_plan_approved_chain_and_latch(client):
    """proposal 승인 → uiux active, uiux 승인 → dev active. 이후 proposal 재승인
    (재수정·재승인 시나리오)에도 래치가 역전되지 않는다."""
    pid = make_project(client, "doclatch")
    with make_session(client) as db:
        init_project_loops(db, pid)
        db.commit()

    with make_session(client) as db:
        on_plan_approved(db, pid, "proposal")
        db.commit()
    st = _statuses(client, pid)
    assert st["proposal"] == DocLoopStatus.DONE
    assert st["uiux-design"] == DocLoopStatus.ACTIVE
    assert st["dev-design"] == DocLoopStatus.LOCKED

    with make_session(client) as db:
        on_plan_approved(db, pid, "uiux-design")
        db.commit()
    st = _statuses(client, pid)
    assert st["uiux-design"] == DocLoopStatus.DONE  # 자기 plan 승인 — done 전환
    assert st["dev-design"] == DocLoopStatus.ACTIVE

    # 래치 — proposal 재승인(재수정·재승인 시나리오): proposal은 done 유지,
    # 이후 문서는 재잠기지 않는다 (done은 done, active·done은 그대로 — 단방향 래치)
    with make_session(client) as db:
        on_plan_approved(db, pid, "proposal")
        db.commit()
    st = _statuses(client, pid)
    assert len(st) == 3
    assert st["proposal"] == DocLoopStatus.DONE
    assert st["uiux-design"] == DocLoopStatus.DONE
    assert st["dev-design"] == DocLoopStatus.ACTIVE


def test_on_plan_approved_reapproval_before_next_unlock_locks_nothing(client):
    """proposal을 두 번 연속 승인(uiux 승인 전) — uiux는 active 유지, dev는 locked 유지."""
    pid = make_project(client, "doclatch2")
    with make_session(client) as db:
        init_project_loops(db, pid)
        db.commit()
    with make_session(client) as db:
        on_plan_approved(db, pid, "proposal")
        on_plan_approved(db, pid, "proposal")  # 재승인 — 재잠금 없음
        db.commit()
    st = _statuses(client, pid)
    assert st["proposal"] == DocLoopStatus.DONE
    assert st["uiux-design"] == DocLoopStatus.ACTIVE
    assert st["dev-design"] == DocLoopStatus.LOCKED


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

    # locked → http_409 계열
    with make_session(client) as db:
        with pytest.raises(CodedHTTPError) as ei:
            require_session_doc(db, pid, "uiux-design")
        assert ei.value.status_code == 409

    # active / done → 통과
    with make_session(client) as db:
        on_plan_approved(db, pid, "proposal")
        db.commit()
    with make_session(client) as db:
        assert require_session_doc(db, pid, "proposal") == "proposal"  # done — 재작업 허용
        assert require_session_doc(db, pid, "uiux-design") == "uiux-design"

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