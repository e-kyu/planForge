# -*- coding: utf-8 -*-
"""docloops 상태 API (파트 1) 테스트 — GET /docloops·ProjectOut 내장·레거시 계약.

step 3부터 create_project가 루프 3행을 시드한다 — "행 없는(레거시) 프로젝트"는
시드 후 행을 지워 만든다 (delete_project_data = projects 삭제 사슬과 같은 경로).
step 4는 문서 세션 생성 게이트(POST /interview/sessions)와 완료 처리 스코프를 잠근다.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from _helpers import insert_plan, make_project, make_session, run_queue
from app.modules.derivatives.infrastructure.models import Build
from app.modules.docloops.facade import delete_project_data, list_loops
from app.modules.interview.infrastructure.models import (
    InterviewSession,
    SessionPhase,
    SessionStatus,
)
from app.modules.plans.facade import PlanOrigin, PlanStatus, create_generation
from fakes import FakeLLM, correct_report_payload, correct_slides_payload, tool_call

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
    assert [d["status"] for d in loops] == ["active", "active", "active"]
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
    """문서 세션 생성 게이트(step 4) — 3종 전부 active로 세션 생성 가능 + 문서별 ws.
    locked는 도달 불가 잔여 상태 — DB 직접 세팅한 행의 안전망 409만 핀한다."""
    pid = make_project(client, "docsession")

    # 미상 slug → 404 (캐노니컬 slug만 허용)
    r = client.post(f"/api/projects/{pid}/interview/sessions",
                    json={"doc_slug": "nonsense"})
    assert r.status_code == 404, r.text

    # 문서 3종 모두 독립 생성 가능 (개발설계서부터 진행해도 된다)
    for slug in DOC_SLUGS:
        r = client.post(f"/api/projects/{pid}/interview/sessions",
                        json={"doc_slug": slug})
        assert r.status_code == 201, r.text
        assert r.json()["doc_slug"] == slug

    # active 문서 — 문서별 워크스페이스 지연 생성
    root = _ws_dir(client) / "docsession" / "proposal"
    for sub in ("work", "output", "docs", "assets"):
        assert (root / sub).is_dir()
    # sources는 문서간 공유라 프로젝트 루트에 유지된다 (DOC_WS_SUBDIRS 계약)
    assert (root / "sources").exists() is False

    # locked 잔여(직접 세팅) → 409 안전망
    from app.modules.docloops.facade import DocLoop, DocLoopStatus

    with make_session(client) as db:
        row = db.scalars(select(DocLoop).where(
            DocLoop.project_id == pid, DocLoop.doc_slug == "uiux-design")).first()
        row.status = DocLoopStatus.LOCKED
        db.commit()
    r = client.post(f"/api/projects/{pid}/interview/sessions",
                    json={"doc_slug": "uiux-design"})
    assert r.status_code == 409, r.text
    assert "잠겨" in r.json()["detail"]


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
    # 생성은 sources 하나만 사전 생성 — 문서 하위 생성도 없다 (무이관 계약)
    assert (wsroot / "sources").is_dir()
    assert not [p for p in wsroot.iterdir() if p.name in (*DOC_SLUGS, "work", "output", "docs", "assets")]


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


# ---------------------------------------------------------------- step 5 — plan 승인의 문서 스코프 (plans-doc-threading)

def _loop_statuses(client, pid: int) -> dict[str, str]:
    return {d["doc_slug"]: d["status"]
            for d in client.get(f"/api/projects/{pid}/docloops").json()}


def _approve_doc_plan(client, app, pid: int, version_no: int,
                      doc_slug: str | None) -> int:
    plan_id = insert_plan(app, pid, version_no, status="draft", doc_slug=doc_slug)
    r = client.post(f"/api/plans/{plan_id}/approve")
    assert r.status_code == 200, r.text
    return plan_id


def test_approval_propagates_doc_loop(client, app):
    """승인 전파(독립 진행) — proposal plan 승인 → proposal만 done·나머지는 active 유지,
    이어 uiux plan 승인 → uiux만 done. 승인 훅은 다른 문서 행을 절대 건드리지 않는다
    (루프 진행 훅은 승인 트랜잭션 안(com.commit 전)에서 docloops.facade.on_plan_approved로만 흐른다)."""
    pid = make_project(client, "docapprovethread")
    _approve_doc_plan(client, app, pid, 1, "proposal")
    assert _loop_statuses(client, pid) == {
        "proposal": "done", "uiux-design": "active", "dev-design": "active"}

    _approve_doc_plan(client, app, pid, 2, "uiux-design")
    assert _loop_statuses(client, pid) == {
        "proposal": "done", "uiux-design": "done", "dev-design": "active"}


def test_reapproval_keeps_independence_and_row_count(client, app):
    """proposal 재승인(세대 교체)에도 다른 문서 행은 불변 — uiux·dev는 active 유지,
    루프 행은 3개 유지."""
    pid = make_project(client, "docapprovelatch")
    _approve_doc_plan(client, app, pid, 1, "proposal")
    _approve_doc_plan(client, app, pid, 2, "uiux-design")

    _approve_doc_plan(client, app, pid, 3, "proposal")  # proposal 새 세대 재승인
    assert _loop_statuses(client, pid) == {
        "proposal": "done", "uiux-design": "done", "dev-design": "active"}
    assert len(client.get(f"/api/projects/{pid}/docloops").json()) == 3


def test_approval_completes_only_scoped_session(client, app):
    """proposal plan 승인 시 PLAN_REVIEW 페이즈인 uiux 세션의 페이즈는 UNCHANGED —
    step 4 complete_plan_review_sessions(doc_slug narrowing) 연동."""
    pid = make_project(client, "docapprovesess")
    with make_session(client) as db:
        p = InterviewSession(project_id=pid, doc_slug="proposal",
                             phase=SessionPhase.PLAN_REVIEW)
        u = InterviewSession(project_id=pid, doc_slug="uiux-design",
                             phase=SessionPhase.PLAN_REVIEW)
        db.add_all([p, u])
        db.commit()
        p_id, u_id = p.id, u.id

    _approve_doc_plan(client, app, pid, 1, "proposal")
    with make_session(client) as db:
        rows = {s.id: s for s in db.scalars(
            select(InterviewSession).where(InterviewSession.project_id == pid)).all()}
        assert rows[p_id].phase == SessionPhase.APPROVED
        assert rows[p_id].status == SessionStatus.DONE
        assert rows[u_id].phase == SessionPhase.PLAN_REVIEW  # 건드리지 않는다
        assert rows[u_id].status != SessionStatus.DONE


def test_approval_writes_doc_scoped_mirror(client, app):
    """문서 plan 승인의 미러는 문서별 하위(ws/{doc_slug}/plan.md)로 기록되고 루트
    plan.md는 만들지 않는다. 레거시(None) plan 승인은 루트 미러를 만든다 (기존 계약)."""
    pid = make_project(client, "docapprovmirror")
    _approve_doc_plan(client, app, pid, 1, "proposal")
    wsroot = _ws_dir(client) / "docapprovmirror"
    assert (wsroot / "proposal" / "plan.md").is_file()
    assert not (wsroot / "plan.md").exists()

    # 레거시(None) plan 승인 — doc_ws_root 계약상 루트 경로
    _approve_doc_plan(client, app, pid, 2, None)
    assert (wsroot / "plan.md").is_file()


def test_supersede_is_doc_scoped(client, app):
    """proposal v1 승인 → uiux plan 승인 → proposal v2 승인: proposal v1만
    superseded가 되고 uiux 승인 plan은 APPROVED로 유지된다 — 전역 SUPERSEDED
    전이의 문서 스코프 축소가 이 테스트의 핵심이다."""
    pid = make_project(client, "docscopesupersede")
    v1 = _approve_doc_plan(client, app, pid, 1, "proposal")
    v2 = _approve_doc_plan(client, app, pid, 2, "uiux-design")
    v3 = _approve_doc_plan(client, app, pid, 3, "proposal")

    plans = {p["id"]: p for p in client.get(f"/api/projects/{pid}/plans").json()}
    assert plans[v1]["status"] == "superseded"
    assert plans[v2]["status"] == "approved"  # 다른 문서 승인본은 유지
    assert plans[v3]["status"] == "approved"

    # ?doc_slug= 필터 — 승인 상태에서도 문서 세대만 좁혀 보인다
    prop = client.get(f"/api/projects/{pid}/plans?doc_slug=proposal").json()
    assert [p["id"] for p in prop] == [v1, v3]
    assert all(p["doc_slug"] == "proposal" for p in prop)


def test_legacy_project_approval_stays_root_path(client, app):
    """doc_loops 행 없는(레거시) 프로젝트의 승인·미러가 전부 루트 경로로 동작한다
    (DB 시드 기준 — 행을 지워 재검증). 승인본 교체 스코프도 None(NULL) 스코프로
    좁혀 기존 동작과 동일하다."""
    pid = _legacy_project(client, "docapprovpregacy")
    v1 = _approve_doc_plan(client, app, pid, 1, None)
    v2 = _approve_doc_plan(client, app, pid, 2, None)

    wsroot = _ws_dir(client) / "docapprovpregacy"
    assert (wsroot / "plan.md").is_file()
    assert not any((wsroot / s).exists() for s in DOC_SLUGS)  # 문서 하위 생성 없음
    assert client.get(f"/api/projects/{pid}/docloops").json() == []

    plans = {p["id"]: p for p in client.get(f"/api/projects/{pid}/plans").json()}
    assert plans[v1]["status"] == "superseded"
    assert plans[v2]["status"] == "approved"


# ---------------------------------------------------------------- step 6 — derive·검수의 문서별 ws

def _doc_derive(client, app, pid: int, kind: str, doc_slug: str | None = None,
                fmts: list[str] | None = None) -> dict:
    """doc_slug 지정 enqueue + run_job 직접 실행 → 최종 job 상태를 반환한다."""
    body: dict = {"kind": kind}
    if doc_slug is not None:
        body["doc_slug"] = doc_slug
    if fmts is not None:
        body["fmts"] = fmts
    r = client.post(f"/api/projects/{pid}/derivatives", json=body)
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    llm = FakeLLM([tool_call("write_slides_json", correct_slides_payload())] if kind == "slides"
                  else [tool_call("write_report_json", correct_report_payload())])
    run_queue(app, llm)
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "done", job
    return job


def test_doc_scoped_derive_writes_doc_workspace_files(client, app, db_env):
    """문서 plan의 derive·빌드 산출물이 문서별 ws(proposal/work·output)에 쌓인다
    (빌더 로직 무변경 — 주입 루트만 문서별로 바뀐다)·Build.doc_slug 채움 +
    file_path "output/..." 상대 형식 유지."""
    pid = make_project(client, "docderive")
    insert_plan(app, pid, 1, doc_slug="proposal")

    slides_job = _doc_derive(client, app, pid, "slides", doc_slug="proposal")
    report_job = _doc_derive(client, app, pid, "report", doc_slug="proposal", fmts=["md"])

    root = _ws_dir(client) / "docderive" / "proposal"
    assert (root / "work" / "slides.json").is_file()
    assert (root / "work" / "report.json").is_file()
    assert list((root / "output").glob("*.pptx"))
    assert list((root / "output").glob("*.md"))
    # 루트 output는 문서별 ws가 채번 소속 — 아예 생성되지도 않는다 (지연 생성 규약)
    assert not (_ws_dir(client) / "docderive" / "output").exists()

    with make_session(app) as db:
        builds = db.scalars(select(Build).where(Build.project_id == pid)).all()
        assert len(builds) == 2  # pptx + md
        assert all(b.doc_slug == "proposal" for b in builds)
        assert all(b.file_path.startswith("output/") for b in builds)
    # job result의 builds도 file_path 계약을 유지한다
    for b in (*slides_job["result"]["builds"], *report_job["result"]["builds"]):
        assert b["file_path"].startswith("output/")


def test_doc_scoped_outputs_listing_and_download(client, app):
    """outputs 목록·다운로드가 문서별 ws 경로에서 파일을 찾는다 (doc-root 결합 보정)."""
    pid = make_project(client, "docoutputfind")
    insert_plan(app, pid, 1, doc_slug="proposal")
    job = _doc_derive(client, app, pid, "report", doc_slug="proposal", fmts=["md"])

    outs = client.get(f"/api/projects/{pid}/outputs").json()
    assert len(outs) == 1 and outs[0]["ext"] == "md"
    build_id = job["result"]["builds"][0]["build_id"]

    r = client.get(f"/api/projects/{pid}/outputs/{build_id}/download")
    assert r.status_code == 200, r.text
    assert "11.5시간" in r.text  # 문서별 ws의 실제 파일을 스트리밍한다 (수치 무결성)


def test_enqueue_derivative_requires_doc_slug_in_doc_loop(client):
    """가드 — doc-loop 프로젝트(has_doc_layout)의 derive enqueue는 doc_slug 필수다.
    None fallback은 문서별 승인본 공존 하에 래치 순서상 오문서 plan을 고르는 결함이므로
    누락은 409, 미상 slug는 404(require_session_doc과 같은 관례)로 거부한다.
    레거시(루프 행 없음)의 None 허용은 test_legacy_doc_none_derive_uses_project_root가 고정."""
    pid = make_project(client, "docderiveguard")

    r = client.post(f"/api/projects/{pid}/derivatives", json={"kind": "report"})
    assert r.status_code == 409, r.text
    assert "doc_slug" in r.json()["detail"]

    r = client.post(f"/api/projects/{pid}/derivatives",
                    json={"kind": "report", "doc_slug": "unknown-doc"})
    assert r.status_code == 404, r.text


def test_outputs_doc_slug_filter(client, app):
    """?doc_slug= 필터 — 문서 루프의 산출물만 좁혀 보인다 (가드로 인해 두 문서 모두
    doc_slug를 실어 derive한다 — None derive는 doc-loop 프로젝트에서 차단됨)."""
    pid = make_project(client, "docoutfilter")
    insert_plan(app, pid, 1, doc_slug="proposal")
    _doc_derive(client, app, pid, "report", doc_slug="proposal", fmts=["md"])
    insert_plan(app, pid, 2, doc_slug="dev-design")
    _doc_derive(client, app, pid, "report", doc_slug="dev-design", fmts=["md"])

    outs = client.get(f"/api/projects/{pid}/outputs").json()
    assert len(outs) == 2
    prop = client.get(f"/api/projects/{pid}/outputs?doc_slug=proposal").json()
    assert len(prop) == 1
    dev = client.get(f"/api/projects/{pid}/outputs?doc_slug=dev-design").json()
    assert len(dev) == 1
    with make_session(app) as db:
        rows = [b.doc_slug for b in db.scalars(
            select(Build).where(Build.project_id == pid)).all()]
        assert rows.count("proposal") == 1
        assert rows.count("dev-design") == 1


def test_review_generation_check_is_doc_scoped(client, app):
    """검수 §2 세대 대응성의 문서 스코프 축소 — 다른 문서(doc_slug 불일치) 빌드는
    '이전 plan 세대' red에서 제외되고, 같은 문서의 이전 세대 빌드는 계속 red다."""
    from app.modules.jobs.facade import JobType, enqueue

    pid = make_project(client, "revdocnar")
    insert_plan(app, pid, 1, doc_slug="proposal")
    _doc_derive(client, app, pid, "slides", doc_slug="proposal")  # proposal 빌드 (v1 세대)
    insert_plan(app, pid, 2, doc_slug="dev-design")
    _doc_derive(client, app, pid, "slides", doc_slug="dev-design")  # 다른 문서 빌드 (v2 세대)
    stale_plan = insert_plan(app, pid, 3, doc_slug="proposal")  # proposal 재승인 — v1 빌드만 stale

    # 검수 잡을 v3 plan으로 직접 큐잉 (review API는 전체 최신 승인본이므로 facade 경유)
    with make_session(app) as db:
        job = enqueue(db, pid, JobType.REVIEW, {"plan_id": stale_plan})
        db.commit()
        review_job_id = job.id
    run_queue(app, FakeLLM([tool_call("report_findings", {"summary": "", "findings": []})] * 2),
              profile="review")

    job = client.get(f"/api/jobs/{review_job_id}").json()
    assert job["status"] == "done", job
    reports = client.get(f"/api/projects/{pid}/reviews").json()
    assert len(reports) == 1
    gen_finds = [f for f in reports[0]["findings"] if f["code"] == "generation"]
    # proposal v1 빌드(stale, 같은 문서)만 보고 — dev-design 빌드는 제외된다
    assert len(gen_finds) == 1 and gen_finds[0]["severity"] == "red"
    assert "재생성" in gen_finds[0]["message"]


def test_legacy_doc_none_derive_uses_project_root(client, app, db_env):
    """회귀 — doc_loops 행 없는(레거시) 프로젝트의 doc_slug=None plan derive는
    기존과 동일하게 프로젝트 루트 work/output을 쓴다 (Build.doc_slug NULL)."""
    pid = _legacy_project(client, "docderivelegacy")
    insert_plan(app, pid, 1, doc_slug=None)

    job = _doc_derive(client, app, pid, "report", fmts=["md"])
    assert job["result"]["counts"]["sections"] == 5

    root = _ws_dir(client) / "docderivelegacy"
    assert (root / "work" / "report.json").is_file()
    assert list((root / "output").glob("*.md"))
    assert not any((root / s).exists() for s in DOC_SLUGS)  # 문서 하위 생성 없음

    outs = client.get(f"/api/projects/{pid}/outputs").json()
    assert len(outs) == 1
    assert (db_env / "docderivelegacy" / outs[0]["file_path"]).is_file()
    with make_session(app) as db:
        builds = db.scalars(select(Build).where(Build.project_id == pid)).all()
        assert len(builds) == 1 and builds[0].doc_slug is None