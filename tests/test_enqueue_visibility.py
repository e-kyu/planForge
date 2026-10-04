# -*- coding: utf-8 -*-
"""잡 큐 진입 202 계약 — POST 응답 시점에 잡 행이 다른 세션에서 보여야 한다.

FastAPI는 yield 의존성(get_db) teardown 커밋을 응답 전송 후에 실행한다. 그래서 잡
enqueue를 반환 전에 커밋하지 않으면 202 직후 프론트의 /jobs refetch가 새 잡을 놓치고
(작업 큐 카드 미생성·버튼 재활성), 잡은 워커가 몰래 처리한 뒤에야 새로고침으로 보인다.
TestClient는 teardown까지 동기 실행해 이 테스트만으로 레이스를 재현하긴 못 하지만,
"응답 시점 가시성" 계약을 기계적으로 고정해 엔드포인트 커밋 누락을 가린다.
"""
from __future__ import annotations

from fakes import plan_sample_markdown


def _approved_plan(db_session_factory, project_id: int) -> int:
    """승인된 plan 행을 직접 적립한다 (test_jobs_worker의 헬퍼와 동일 계약)."""
    from app.modules.plans.infrastructure.models import Plan, PlanOrigin, PlanStatus

    with db_session_factory() as s:
        plan = Plan(project_id=project_id, version_no=1,
                    markdown=plan_sample_markdown(), docs=["제안서"],
                    parsed_ok=True, status=PlanStatus.APPROVED, origin=PlanOrigin.EDIT)
        s.add(plan)
        s.commit()
        return plan.id


def _seed_derivative(db_session_factory, plan_id: int, project_id: int) -> None:
    """검수 enqueue 게이트(has_any) 통과용 파생물 행 — 잡은 실행하지 않는다."""
    from app.modules.derivatives.infrastructure.models import Derivative, DerivativeKind

    with db_session_factory() as s:
        s.add(Derivative(plan_id=plan_id, project_id=project_id,
                         kind=DerivativeKind.REPORT, doc="제안서", json={}))
        s.commit()


def test_derive_enqueue_visible_to_other_session(client, app):
    from app.modules.jobs.infrastructure.models import Job, JobStatus
    from app.shared.db import make_session_factory

    client.post("/api/projects", json={"slug": "vis-derive", "title": "가시"})
    _approved_plan(make_session_factory(app.state.settings.database_url), 1)

    r = client.post("/api/projects/1/derivatives", json={"kind": "report", "fmts": ["md"]})
    assert r.status_code == 202
    job_id = r.json()["id"]

    # 응답과 무관한 새 세션에서 행이 보인다 — 커밋이 응답에 선행한다는 계약.
    with make_session_factory(app.state.settings.database_url)() as s:
        job = s.get(Job, job_id)
        assert job is not None
        assert job.status == JobStatus.QUEUED


def test_review_enqueue_visible_to_other_session(client, app):
    from app.modules.jobs.infrastructure.models import Job, JobStatus
    from app.shared.db import make_session_factory

    factory = make_session_factory(app.state.settings.database_url)
    client.post("/api/projects", json={"slug": "vis-review", "title": "가시"})
    plan_id = _approved_plan(factory, 1)
    _seed_derivative(factory, plan_id, 1)

    r = client.post("/api/projects/1/reviews")
    assert r.status_code == 202
    job_id = r.json()["id"]

    with factory() as s:
        job = s.get(Job, job_id)
        assert job is not None
        assert job.status == JobStatus.QUEUED