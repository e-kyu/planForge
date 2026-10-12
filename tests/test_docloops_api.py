# -*- coding: utf-8 -*-
"""docloops 상태 API (파트 1) 테스트 — GET /docloops·ProjectOut 내장·레거시 계약.

step 3부터 create_project가 루프 3행을 시드한다 — "행 없는(레거시) 프로젝트"는
시드 후 행을 지워 만든다 (delete_project_data = projects 삭제 사슬과 같은 경로).
step 4는 문서 세션 생성 게이트(POST /interview/sessions)와 완료 처리 스코프를 잠근다.
"""
from __future__ import annotations

from pathlib import Path

from _helpers import make_project, make_session
from app.modules.docloops.facade import delete_project_data, list_loops
from app.modules.plans.facade import PlanOrigin, PlanStatus, create_generation

DOC_SLUGS = ["proposal", "uiux-design", "dev-design"]


def _ws_dir(client) -> Path:
    return Path(client.app.state.settings.workspaces_dir)


def _legacy_project(client, slug: str) -> int:
    pid = make_project(client, slug)
    with make_session(client) as db:
        delete_project_data(db, pid)
        db.commit()
    return pid


def test_created_project_docloops_order_labels_and_null_versions(client):
    r = client.post("/api/projects", json={"slug": "docapi", "title": "문서"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    # 생성 응답에도 docloops가 내장된다 (ProjectOut 기본 확장)
    assert [d["doc_slug"] for d in r.json()["docloops"]] == DOC_SLUGS

    r = client.get(f"/api/projects/{pid}/docloops")
    assert r.status_code == 200, r.text
    loops = r.json()
    assert len(loops) == 3
    assert [d["doc_slug"] for d in loops] == DOC_SLUGS  # DOC_KINDS 정렬
    assert [d["status"] for d in loops] == ["active", "locked", "locked"]
    assert [d["label"] for d in loops] == ["제안서", "UI·UX설계서", "개발설계서"]
    assert all(d["plan_version"] is None and d["plan_id"] is None for d in loops)


def test_project_list_and_detail_embed_docloops(client):
    make_project(client, "doclist1")
    pid2 = make_project(client, "doclist2")

    rows = client.get("/api/projects").json()
    assert len(rows) == 2
    for p in rows:
        assert [d["doc_slug"] for d in p["docloops"]] == DOC_SLUGS
        assert p["docloops"][0]["status"] == "active"

    r = client.get(f"/api/projects/{pid2}")
    assert [d["doc_slug"] for d in r.json()["docloops"]] == DOC_SLUGS
    assert r.json()["docloops"][0]["status"] == "active"  # 단건도 동일 데이터


def test_legacy_project_without_rows_returns_empty(client):
    pid = _legacy_project(client, "doclegacyapi")
    assert client.get(f"/api/projects/{pid}/docloops").json() == []
    # 목록·단건 내장 — 프론트는 빈 목록을 "레거시 프로젝트"로 보고 문서 버튼을 렌더링하지 않는다
    rows = client.get("/api/projects").json()
    assert {p["id"]: p for p in rows}[pid]["docloops"] == []
    assert client.get(f"/api/projects/{pid}").json()["docloops"] == []


def test_unknown_project_docloops_404(client):
    assert client.get("/api/projects/999/docloops").status_code == 404


def test_plan_versions_are_generation_ref_not_cache(client):
    """plan_version·plan_id는 plans 행 역참조 파생값 (루프 행에 캐시하지 않는다)."""
    pid = make_project(client, "docver")
    with make_session(client) as db:
        g1 = create_generation(db, pid, markdown="# v1", docs=["제안서"],
                               parsed_ok=True, origin=PlanOrigin.EDIT,
                               doc_slug="proposal")
        db.commit()
        g1_id, g1_ver = g1.id, g1.version_no
    proposal, uiux, dev = client.get(f"/api/projects/{pid}/docloops").json()
    assert proposal["plan_version"] == 1 and proposal["plan_id"] == g1_id
    assert uiux["plan_version"] is None and uiux["plan_id"] is None
    assert dev["plan_version"] is None

    # proposal 재생성 — 최신(2)을 가리킨다. version_no는 프로젝트 전체 단조 (uq_project_planver)
    with make_session(client) as db:
        g2 = create_generation(db, pid, markdown="# v2", docs=["제안서"],
                               parsed_ok=True, origin=PlanOrigin.EDIT,
                               status=PlanStatus.APPROVED, doc_slug="proposal")
        db.commit()
        g2_id, g2_ver = g2.id, g2.version_no
    assert g2_ver == 2 and g1_ver == 1
    proposal, _, _ = client.get(f"/api/projects/{pid}/docloops").json()
    assert proposal["plan_version"] == 2 and proposal["plan_id"] == g2_id


def test_delete_project_removes_docloop_rows(client):
    pid = make_project(client, "docdeleteapi")
    with make_session(client) as db:
        assert len(list_loops(db, pid)) == 3

    assert client.delete(f"/api/projects/{pid}").status_code == 204
    with make_session(client) as db:
        assert list_loops(db, pid) == []


def test_create_doc_session_gates_and_layout(client):
    """문서 세션 생성 게이트(step 4) — locked 409·미상 slug 404·active 201 + 문서별 ws."""
    pid = make_project(client, "docsession")

    # locked 문서 (uiux-design) → 409 + 이전 문서 승인 안내
    r = client.post(f"/api/projects/{pid}/interview/sessions",
                    json={"doc_slug": "uiux-design"})
    assert r.status_code == 409, r.text
    assert "잠겨" in r.json()["detail"]

    # 미상 slug → 404 (캐노니컬 slug만 허용)
    r = client.post(f"/api/projects/{pid}/interview/sessions",
                    json={"doc_slug": "nonsense"})
    assert r.status_code == 404, r.text

    # active 문서 (proposal) → 201 + 문서별 워크스페이스 지연 생성
    r = client.post(f"/api/projects/{pid}/interview/sessions",
                    json={"doc_slug": "proposal"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["doc_slug"] == "proposal"
    root = _ws_dir(client) / "docsession" / "proposal"
    for sub in ("work", "output", "docs", "assets"):
        assert (root / sub).is_dir()
    # sources는 문서간 공유라 프로젝트 루트에 유지된다 (DOC_WS_SUBDIRS 계약)
    assert (root / "sources").exists() is False


def test_create_session_without_doc_slug_keeps_legacy_layout(client):
    """doc_slug 없는 세션 — doc_slug null, 문서별 디렉터리를 만들지 않는다 (레거시 계약)."""
    pid = make_project(client, "docsesslegacy")
    r = client.post(f"/api/projects/{pid}/interview/sessions", json={})
    assert r.status_code == 201, r.text
    assert r.json()["doc_slug"] is None
    wsroot = _ws_dir(client) / "docsesslegacy"
    assert not [p for p in wsroot.iterdir() if p.name in DOC_SLUGS]


def test_create_doc_session_on_legacy_project_saves_slug_only(client):
    """레거시 프로젝트(doc_loops 행 없음)의 doc 세션 — 409/404가 아니라 slug만 저장되고
    미러는 루트 경로를 유지한다 (기존 프로젝트 무이관 계약)."""
    pid = _legacy_project(client, "docsesslegacyproj")
    r = client.post(f"/api/projects/{pid}/interview/sessions",
                    json={"doc_slug": "dev-design"})
    assert r.status_code == 201, r.text
    assert r.json()["doc_slug"] == "dev-design"
    wsroot = _ws_dir(client) / "docsesslegacyproj"
    for sub in ("work", "output", "docs", "sources", "assets"):
        assert (wsroot / sub).is_dir()  # create_workspace의 원본 5개 — 문서 하위 생성 없음
    assert not (wsroot / "dev-design").exists()


def test_list_plans_doc_slug_filter(client):
    pid = make_project(client, "docfilter")
    with make_session(client) as db:
        create_generation(db, pid, markdown="# a", origin=PlanOrigin.EDIT,
                          doc_slug="proposal")
        create_generation(db, pid, markdown="# b", origin=PlanOrigin.EDIT,
                          doc_slug="dev-design")
        create_generation(db, pid, markdown="# c", origin=PlanOrigin.EDIT)  # 레거시(None)
        db.commit()

    all_rows = client.get(f"/api/projects/{pid}/plans")
    assert [(p["version_no"], p["doc_slug"]) for p in all_rows.json()] == [
        (1, "proposal"), (2, "dev-design"), (3, None)]

    prop = client.get(f"/api/projects/{pid}/plans?doc_slug=proposal").json()
    assert len(prop) == 1 and prop[0]["doc_slug"] == "proposal"
    dev = client.get(f"/api/projects/{pid}/plans?doc_slug=dev-design").json()
    assert len(dev) == 1 and dev[0]["doc_slug"] == "dev-design"