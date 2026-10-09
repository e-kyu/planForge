# -*- coding: utf-8 -*-
"""잡 큐 진입 202 계약 — POST 응답 시점에 잡 행이 다른 세션에서 보여야 한다.

FastAPI는 yield 의존성(get_db) teardown 커밋을 응답 전송 후에 실행한다. 그래서 잡
enqueue를 반환 전에 커밋하지 않으면 202 직후 프론트의 /jobs refetch가 새 잡을 놓치고
(작업 큐 카드 미생성·버튼 재활성), 잡은 워커가 몰래 처리한 뒤에야 새로고침으로 보인다.
TestClient는 teardown까지 동기 실행해 이 테스트만으로 레이스를 재현하긴 못 하지만,
"응답 시점 가시성" 계약을 기계적으로 고정해 엔드포인트 커밋 누락을 가린다.
"""
from __future__ import annotations

from _helpers import insert_plan, make_project, session_factory


def _seed_derivative(app, plan_id: int, project_id: int) -> None:
    """검수 enqueue 게이트(has_any) 통과용 파생물 행 — 잡은 실행하지 않는다."""
    from app.modules.derivatives.infrastructure.models import Derivative, DerivativeKind

    with session_factory(app)() as s:
        s.add(Derivative(plan_id=plan_id, project_id=project_id,
                         kind=DerivativeKind.REPORT, doc="제안서", json={}))
        s.commit()


def test_derive_enqueue_visible_to_other_session(client, app):
    from app.modules.jobs.infrastructure.models import Job, JobStatus

    make_project(client, "vis-derive", "가시")
    insert_plan(app, 1)

    r = client.post("/api/projects/1/derivatives", json={"kind": "report", "fmts": ["md"]})
    assert r.status_code == 202
    job_id = r.json()["id"]

    # 응답과 무관한 새 세션에서 행이 보인다 — 커밋이 응답에 선행한다는 계약.
    with session_factory(app)() as s:
        job = s.get(Job, job_id)
        assert job is not None
        assert job.status == JobStatus.QUEUED


def test_review_enqueue_visible_to_other_session(client, app):
    from app.modules.jobs.infrastructure.models import Job, JobStatus

    make_project(client, "vis-review", "가시")
    plan_id = insert_plan(app, 1)
    _seed_derivative(app, plan_id, 1)

    r = client.post("/api/projects/1/reviews")
    assert r.status_code == 202
    job_id = r.json()["id"]

    with session_factory(app)() as s:
        job = s.get(Job, job_id)
        assert job is not None
        assert job.status == JobStatus.QUEUED