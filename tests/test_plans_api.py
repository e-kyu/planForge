# -*- coding: utf-8 -*-
"""plan API 테스트 — 승인 게이트(FR-2.9)·세대 교체·수정 게이트(FR-4.3)."""
from __future__ import annotations

from fakes import plan_sample_markdown


def _make_project(client) -> int:
    client.post("/api/projects", json={"slug": "plan-demo", "title": "plan 데모"})
    return 1


def _insert_plan(app, project_id: int, version_no: int = 1, status: str = "draft") -> int:
    from app.db import make_session_factory
    from app.models import Plan, PlanOrigin, PlanStatus

    with make_session_factory(app.state.settings.database_url)() as s:
        plan = Plan(project_id=project_id, version_no=version_no,
                    markdown=plan_sample_markdown(), docs=["제안서", "개발설계서"],
                    parsed_ok=True, status=PlanStatus(status), origin=PlanOrigin.INTERVIEW)
        s.add(plan)
        s.commit()
        return plan.id


def test_list_and_get_plans(client, app):
    pid = _make_project(client)
    _insert_plan(app, pid, 1)
    r = client.get(f"/api/projects/{pid}/plans")
    assert r.status_code == 200 and len(r.json()) == 1
    assert r.json()[0]["version_no"] == 1 and r.json()[0]["status"] == "draft"


def test_approve_flow_and_supersede(client, app, db_env):
    pid = _make_project(client)
    v1 = _insert_plan(app, pid, 1)
    assert client.post(f"/api/plans/{v1}/approve").status_code == 200

    # 승인 후 재승인 → 409
    assert client.post(f"/api/plans/{v1}/approve").status_code == 409

    # plan.md 미러 생성 (SSOT의 파일 형태)
    assert (db_env / "plan-demo" / "plan.md").is_file()

    # 수정 → 새 세대 DRAFT (FR-4.3)
    md = plan_sample_markdown()
    r = client.post(f"/api/plans/{v1}/revise", json={"markdown": md})
    assert r.status_code == 201, r.text
    v2 = r.json()["id"]
    assert r.json()["version_no"] == 2 and r.json()["status"] == "draft"
    assert r.json()["origin"] == "edit"

    # v2 승인 → v1은 세대 교체(SUPERSEDED)
    assert client.post(f"/api/plans/{v2}/approve").status_code == 200
    plans = {p["id"]: p for p in client.get(f"/api/projects/{pid}/plans").json()}
    assert plans[v1]["status"] == "superseded"
    assert plans[v2]["status"] == "approved"
    assert plans[v2]["approved_at"] is not None


def test_revise_invalid_markdown_422(client, app):
    pid = _make_project(client)
    plan_id = _insert_plan(app, pid, 1)
    bad = "# 기획\n\n## 메타\n- 목적: x\n\n## 핵심 메시지 (3개)\n1. a\n\n## 슬라이드 목록\n"
    r = client.post(f"/api/plans/{plan_id}/revise", json={"markdown": bad})
    assert r.status_code == 422
    assert "plan 포맷 검증 실패" in r.json()["detail"]

    # 파싱은 통과하지만 핵심 메시지가 3개가 아니면 422 (FR-2.8)
    md = plan_sample_markdown().replace(
        "3. 시범 도입으로 효과를 먼저 검증한 뒤 확장한다\n", "")
    r = client.post(f"/api/plans/{plan_id}/revise", json={"markdown": md})
    assert r.status_code == 422
    assert "핵심 메시지는 정확히 3개" in r.json()["detail"]


def test_plan_404(client):
    assert client.get("/api/plans/999").status_code == 404
    assert client.post("/api/plans/999/approve").status_code == 404