# -*- coding: utf-8 -*-
"""테스트 공용 헬퍼 — DB 적립·잡 큐 실행 시드 함수.

규칙: 테스트 파일 간 import 금지 — 공용 로직은 이 모듈로 모은다. fake LLM·샘플
마크다운은 fakes.py, app/client·db_env fixture는 conftest.py 소유(여기서 만들지 않는다).
"""
from __future__ import annotations

from fakes import plan_sample_markdown


def make_project(client, slug: str, title: str = "x") -> int:
    """프로젝트를 만들고 id를 돌려준다 — 생성 실패는 어설션으로 즉시 드러낸다."""
    r = client.post("/api/projects", json={"slug": slug, "title": title})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def session_factory(app):
    """app(또는 TestClient — .app을 따라간다)의 DB 세션 팩토리."""
    target = app.app if hasattr(app, "app") else app
    from app.shared.db import make_session_factory

    return make_session_factory(target.state.settings.database_url)


def make_session(app):
    """DB 세션을 연다 — `with make_session(app) as s:` 형태로 쓴다."""
    return session_factory(app)()


def insert_plan(app, project_id, version_no=1, *, status="approved", origin="edit",
                docs=("제안서",), markdown=None) -> int:
    """plan 행을 직접 적립해 plan.id를 돌려준다 (승인 게이트 통과용 시드 — plan 생성·
    수정 API가 아닌 직접 적립). status·origin은 API 문자열과 같은 소문자 값을 받는다."""
    from app.modules.plans.infrastructure.models import Plan, PlanOrigin, PlanStatus

    with session_factory(app)() as s:
        plan = Plan(project_id=project_id, version_no=version_no,
                    markdown=markdown or plan_sample_markdown(),
                    docs=list(docs), parsed_ok=True,
                    status=PlanStatus(status), origin=PlanOrigin(origin))
        s.add(plan)
        s.commit()
        return plan.id


def run_queue(app, llm, profile="derive"):
    """큐에서 잡 하나를 꺾아 실행한다 — 테스트는 워커 루프 대신 이 함수로 결정론 실행."""
    from app.modules.jobs.application.worker import JobContext, claim_next_job, run_job
    from app.shared.config import get_settings

    ctx = JobContext(
        session_factory=session_factory(app),
        settings=get_settings(),
        llm_overrides={profile: llm},
    )
    s = ctx.session_factory()
    try:
        job = claim_next_job(s)
        if job is not None:
            run_job(ctx, job)
    finally:
        s.close()


def run_derive(app, client, pid: int, kind: str, llm, *, fmts=None) -> int:
    """파생물 잡을 enqueue하고 즉시 큐를 실행해 잡 id를 돌려준다 (e2e 시드)."""
    body = {"kind": kind}
    if fmts:
        body["fmts"] = fmts
    r = client.post(f"/api/projects/{pid}/derivatives", json=body)
    assert r.status_code == 202, r.text
    run_queue(app, llm)
    return r.json()["id"]