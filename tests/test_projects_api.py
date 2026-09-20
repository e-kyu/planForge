# -*- coding: utf-8 -*-
"""프로젝트 API (FR-1) 테스트."""
from __future__ import annotations


def test_create_project_makes_workspace(client, db_env):
    r = client.post("/api/projects", json={"slug": "demo-proj", "title": "데모 프로젝트"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["slug"] == "demo-proj"
    assert body["status"] == "active"
    for sub in ("work", "output", "docs", "sources", "assets"):
        assert (db_env / "demo-proj" / sub).is_dir(), sub


def test_create_project_duplicate_slug_conflict(client, db_env):
    client.post("/api/projects", json={"slug": "dup", "title": "첫"})
    r = client.post("/api/projects", json={"slug": "dup", "title": "둘"})
    assert r.status_code == 409


def test_create_project_bad_slug_rejected(client, db_env):
    for bad in ("UPPER", "has_underscore", "-leading-hyphen", "한글", ""):
        r = client.post("/api/projects", json={"slug": bad, "title": "x"})
        assert r.status_code == 422, bad


def test_list_and_get_projects(client, db_env):
    client.post("/api/projects", json={"slug": "p1", "title": "일"})
    client.post("/api/projects", json={"slug": "p2", "title": "이", "owner": "kim"})
    r = client.get("/api/projects")
    assert [p["slug"] for p in r.json()] == ["p1", "p2"]
    r = client.get("/api/projects?status=archived")
    assert r.json() == []
    r = client.get("/api/projects/2")
    assert r.json()["owner"] == "kim"
    r = client.get("/api/projects/999")
    assert r.status_code == 404


def test_patch_project_archive(client, db_env):
    client.post("/api/projects", json={"slug": "arch", "title": "보관"})
    r = client.patch("/api/projects/1", json={"status": "archived", "title": "보관됨"})
    assert r.json()["status"] == "archived"
    assert r.json()["title"] == "보관됨"


# ---------------------------------------------------------------- 삭제 (FR-1 확장)

def _session_factory(client):
    from app.db import make_session_factory

    return make_session_factory(client.app.state.settings.database_url)


def _seed_children(client):
    """추적성 사슬 전체를 적립한다: 세션→메시지, 팩트, plan, 파생물, 빌드, 검수, job(done)."""
    from sqlalchemy import select, func
    from app.models import (
        Build, Derivative, DerivativeKind, Fact, InterviewMessage,
        InterviewSession, Job, JobStatus, JobType, MessageKind, MessageRole,
        Plan, ReviewReport,
    )

    sf = _session_factory(client)
    with sf() as s:
        sess = InterviewSession(project_id=1)
        s.add(sess)
        s.flush()
        s.add(InterviewMessage(session_id=sess.id, seq=1, role=MessageRole.USER,
                               kind=MessageKind.TEXT, content="m1"))
        s.add(Fact(project_id=1, content="보고 작성 주 10시간", source="인터뷰"))
        plan = Plan(project_id=1, version_no=1, markdown="# plan")
        s.add(plan)
        s.flush()
        der = Derivative(plan_id=plan.id, project_id=1, kind=DerivativeKind.SLIDES,
                         doc="제안서", json={})
        s.add(der)
        s.flush()
        s.add(Build(project_id=1, plan_id=plan.id, derivative_id=der.id,
                    doc_kind="제안서", ext="pptx", version_no=1, title="제안_v01",
                    file_path="output/제안_v01.pptx"))
        s.add(ReviewReport(project_id=1, plan_id=plan.id, findings=[]))
        s.add(Job(project_id=1, type=JobType.DERIVE_BUILD, status=JobStatus.DONE,
                  payload={}))
        s.commit()

    def counts():
        with sf() as s:
            return {m.__name__: s.scalar(select(func.count()).select_from(m))
                    for m in (InterviewSession, InterviewMessage, Fact, Plan,
                              Derivative, Build, ReviewReport, Job)}

    return counts


def test_delete_project_cascades_and_removes_workspace(client, db_env):
    client.post("/api/projects", json={"slug": "gone", "title": "지울 프로젝트"})
    counts = _seed_children(client)

    r = client.delete("/api/projects/1")
    assert r.status_code == 204, r.text
    assert client.get("/api/projects/1").status_code == 404
    assert client.get("/api/projects").json() == []
    assert not (db_env / "gone").exists()  # 워크스페이스 제거
    assert all(n == 0 for n in counts().values()), counts()


def test_delete_project_blocked_by_active_job(client, db_env):
    client.post("/api/projects", json={"slug": "busy", "title": "실행 중"})
    from app.models import Job, JobStatus, JobType

    with _session_factory(client)() as s:
        s.add(Job(project_id=1, type=JobType.REVIEW, status=JobStatus.QUEUED,
                  payload={}))
        s.commit()
    r = client.delete("/api/projects/1")
    assert r.status_code == 409, r.text
    assert client.get("/api/projects/1").status_code == 200  # 삭제되지 않음


def test_delete_project_404(client, db_env):
    assert client.delete("/api/projects/999").status_code == 404


def test_deleted_slug_and_workspace_reusable(client, db_env):
    client.post("/api/projects", json={"slug": "reuse", "title": "첫"})
    assert client.delete("/api/projects/1").status_code == 204
    r = client.post("/api/projects", json={"slug": "reuse", "title": "재생성"})
    assert r.status_code == 201, r.text
    assert (db_env / "reuse" / "work").is_dir()


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}