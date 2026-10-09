# -*- coding: utf-8 -*-
"""plan API 테스트 — 승인 게이트(FR-2.9)·세대 교체·수정 게이트(FR-4.3)."""
from __future__ import annotations

from fakes import plan_sample_markdown, plan_skeleton_bad_markdown
from _helpers import insert_plan, make_project


def test_list_and_get_plans(client, app):
    pid = make_project(client, "plan-demo", "plan 데모")
    insert_plan(app, pid, 1, status="draft", origin="interview",
                docs=("제안서", "개발설계서"))
    r = client.get(f"/api/projects/{pid}/plans")
    assert r.status_code == 200 and len(r.json()) == 1
    assert r.json()[0]["version_no"] == 1 and r.json()[0]["status"] == "draft"


def test_approve_flow_and_supersede(client, app, db_env):
    pid = make_project(client, "plan-demo", "plan 데모")
    v1 = insert_plan(app, pid, 1, status="draft", origin="interview",
                     docs=("제안서", "개발설계서"))
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
    pid = make_project(client, "plan-demo", "plan 데모")
    plan_id = insert_plan(app, pid, 1, status="draft", origin="interview",
                          docs=("제안서", "개발설계서"))
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

    # 파싱은 통과하지만 골격이 미달이면 422 — 단일 권위가 SkeletonError를 문서명 포함
    # PlanError로 감싼다 (전파되면 500이 됐던 결함의 잠금)
    # fixtures/plan.skeleton_bad.md — 표지·목차·마무리 누락 (메타 산출 문서 생략 → 기본 문서 fallback)
    skel = plan_skeleton_bad_markdown()
    r = client.post(f"/api/plans/{plan_id}/revise", json={"markdown": skel})
    assert r.status_code == 422
    assert "plan 골격 검증 실패" in r.json()["detail"]
    assert "문서 '제안서'" in r.json()["detail"]

    # 메타 '산출 문서' 라인 유실(다중 문서) — 파서 교차검증이 422로 막는다. 유실을 무음
    # default(["제안서"])로 격하시키면 derive가 나머지 문서를 통째로 버린다 (실세션 수업)
    md = plan_sample_markdown().replace("- 산출 문서: 제안서, 개발설계서\n", "")
    r = client.post(f"/api/plans/{plan_id}/revise", json={"markdown": md})
    assert r.status_code == 422
    assert "슬라이드 문서 태그 '개발설계서'가 메타 '산출 문서'" in r.json()["detail"]


def test_plan_404(client):
    assert client.get("/api/plans/999").status_code == 404
    assert client.post("/api/plans/999/approve").status_code == 404