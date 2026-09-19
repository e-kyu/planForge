# -*- coding: utf-8 -*-
"""검수 → plan 반영 테스트 (FR-4.3) — 게이트·정상 흐름·검증 실패·부분 선택."""
from __future__ import annotations

from fakes import FakeLLM, plan_sample_markdown, tool_call
from test_review import _approved_plan, _run_queue

SAMPLE = plan_sample_markdown()
REVISED = SAMPLE.replace(
    "3. 시범 도입으로 효과를 먼저 검증한 뒤 확장한다\n",
    "3. 시범 도입으로 효과를 먼저 검증한 뒤 확장한다 — 4분기 시범 착수\n",
)

FINDINGS = [
    {"severity": "red", "code": "numeric-extra", "where": "슬라이드 3 (표)",
     "message": "plan에 없는 수치가 등장했다", "suggestion": "표 데이터를 팩트와 대조해 교정"},
    {"severity": "yellow", "code": "style", "where": "슬라이드 5",
     "message": "문체가 불일치한다"},
]


def _make_project(client, slug: str) -> int:
    client.post("/api/projects", json={"slug": slug, "title": "x"})
    return 1


def _review_report(app, project_id: int, plan_id: int, findings: list[dict]) -> int:
    from app.db import make_session_factory
    from app.models import ReviewReport

    with make_session_factory(app.state.settings.database_url)() as s:
        rep = ReviewReport(
            project_id=project_id, plan_id=plan_id, findings=findings,
            red_count=sum(1 for f in findings if f["severity"] == "red"),
            yellow_count=sum(1 for f in findings if f["severity"] == "yellow"),
            white_count=sum(1 for f in findings if f["severity"] == "white"),
            llm_ok=True, summary="총평",
        )
        s.add(rep)
        s.commit()
        return rep.id


def test_revise_from_review_contract_exposes_suggestion(client, app):
    """LLM 발견사항의 suggestion이 API 응답에 노출된다 (계약 보강)."""
    pid = _make_project(client, "prv-contract")
    plan_id = _approved_plan(app, pid)
    _review_report(app, pid, plan_id, FINDINGS)
    rep = client.get(f"/api/projects/{pid}/reviews").json()[0]
    assert rep["findings"][0]["suggestion"] == "표 데이터를 팩트와 대조해 교정"
    assert rep["findings"][1]["suggestion"] is None  # 결정론 발견사항엔 제안이 없다


def test_revise_from_review_gates(client, app):
    from app.db import make_session_factory
    from app.models import Plan, PlanOrigin, PlanStatus

    pid = _make_project(client, "prv-gate")
    # plan 404
    r = client.post("/api/plans/999/revise-from-review", json={"review_id": 1})
    assert r.status_code == 404

    plan_id = _approved_plan(app, pid)
    rid = _review_report(app, pid, plan_id, FINDINGS)

    # review 404
    r = client.post(f"/api/plans/{plan_id}/revise-from-review", json={"review_id": 999})
    assert r.status_code == 404

    # 세대 불일치 — 다른 plan 세대에 반영 시도
    with make_session_factory(app.state.settings.database_url)() as s:
        other = Plan(project_id=pid, version_no=2, markdown=SAMPLE, docs=["제안서"],
                     parsed_ok=True, status=PlanStatus.DRAFT, origin=PlanOrigin.EDIT)
        s.add(other)
        s.commit()
        other_id = other.id
    r = client.post(f"/api/plans/{other_id}/revise-from-review", json={"review_id": rid})
    assert r.status_code == 409

    # indices 무효·중복·빈 선택
    r = client.post(f"/api/plans/{plan_id}/revise-from-review",
                    json={"review_id": rid, "finding_indices": [5]})
    assert r.status_code == 409
    r = client.post(f"/api/plans/{plan_id}/revise-from-review",
                    json={"review_id": rid, "finding_indices": [0, 0]})
    assert r.status_code == 409
    r = client.post(f"/api/plans/{plan_id}/revise-from-review",
                    json={"review_id": rid, "finding_indices": []})
    assert r.status_code == 409

    # 정상 게이트 → 202 + plan_revise 잡
    r = client.post(f"/api/plans/{plan_id}/revise-from-review",
                    json={"review_id": rid, "finding_indices": [1]})
    assert r.status_code == 202, r.text
    assert r.json()["type"] == "plan_revise"


def test_revise_from_review_happy_path(client, app, db_env):
    pid = _make_project(client, "prv-happy")
    plan_id = _approved_plan(app, pid)
    rid = _review_report(app, pid, plan_id, FINDINGS)

    r = client.post(f"/api/plans/{plan_id}/revise-from-review",
                    json={"review_id": rid, "finding_indices": [0]})
    assert r.status_code == 202
    job_id = r.json()["id"]

    llm = FakeLLM([tool_call("write_plan", {"markdown": REVISED})])
    _run_queue(app, llm, profile="plan_revise")

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "done", job
    assert job["result"]["version_no"] == 2 and job["result"]["applied_count"] == 1

    # 새 세대: DRAFT, origin=review / base plan 무변경
    from app.db import make_session_factory
    from app.models import Plan, PlanOrigin, PlanStatus

    with make_session_factory(app.state.settings.database_url)() as s:
        rows = {p.id: p for p in s.query(Plan).all()}
    base = next(p for p in rows.values() if p.id == plan_id)
    fresh = next(p for p in rows.values() if p.id == job["result"]["plan_id"])
    assert fresh.status == PlanStatus.DRAFT and fresh.origin == PlanOrigin.REVIEW
    assert fresh.version_no == 2 and fresh.parsed_ok is True
    assert base.markdown == SAMPLE and base.status.value == "approved"

    # SSOT 미러 갱신
    mirror = db_env / "prv-happy" / "plan.md"
    assert mirror.is_file() and mirror.read_text(encoding="utf-8-sig") == REVISED

    # LLM 컨텍스트: 선택 발견사항(+제안)만 포함 — 미선택 발견사항은 제외
    user_ctx = llm.calls[0][-1]["content"]
    assert "plan에 없는 수치가 등장했다" in user_ctx
    assert "표 데이터를 팩트와 대조해 교정" in user_ctx
    assert "문체가 불일치한다" not in user_ctx
    assert SAMPLE in user_ctx  # plan 전문이 기준으로 전달된다


def test_revise_from_review_no_indices_means_all(client, app):
    pid = _make_project(client, "prv-all")
    plan_id = _approved_plan(app, pid)
    rid = _review_report(app, pid, plan_id, FINDINGS)

    r = client.post(f"/api/plans/{plan_id}/revise-from-review", json={"review_id": rid})
    assert r.status_code == 202
    llm = FakeLLM([tool_call("write_plan", {"markdown": REVISED})])
    _run_queue(app, llm, profile="plan_revise")

    user_ctx = llm.calls[0][-1]["content"]
    assert "plan에 없는 수치가 등장했다" in user_ctx
    assert "문체가 불일치한다" in user_ctx  # 전체 선택
    client.get(f"/api/jobs/{r.json()['id']}")
    job = client.get(f"/api/jobs/{r.json()['id']}").json()
    assert job["status"] == "done" and job["result"]["applied_count"] == 2


def test_revise_from_review_nudge_then_success(client, app):
    pid = _make_project(client, "prv-nudge")
    plan_id = _approved_plan(app, pid)
    rid = _review_report(app, pid, plan_id, FINDINGS)

    client.post(f"/api/plans/{plan_id}/revise-from-review", json={"review_id": rid})
    llm = FakeLLM([
        {"content": "도구를 못 찾겠습니다", "tool_calls": []},
        tool_call("write_plan", {"markdown": REVISED}),
    ])
    _run_queue(app, llm, profile="plan_revise")
    job = client.get("/api/jobs/1").json()
    assert job["status"] == "done", job


def test_revise_from_review_validation_failure_fails_job(client, app):
    pid = _make_project(client, "prv-invalid")
    plan_id = _approved_plan(app, pid)
    rid = _review_report(app, pid, plan_id, FINDINGS)

    client.post(f"/api/plans/{plan_id}/revise-from-review", json={"review_id": rid})
    # 핵심 메시지 3개 위반 마크다운 3회 → 재시도 소진
    bad = SAMPLE.replace("3. 시범 도입으로 효과를 먼저 검증한 뒤 확장한다\n", "")
    llm = FakeLLM([tool_call("write_plan", {"markdown": bad})] * 3)
    _run_queue(app, llm, profile="plan_revise")

    job = client.get("/api/jobs/1").json()
    assert job["status"] == "failed"
    assert job["error_class"] == "llm"  # 재시도 소진 — LLM이 유효 plan을 못 만듦
    assert "plan 포맷 검증 실패" in job["error"]

    # 새 Plan 세대가 만들어지지 않았다
    plans = client.get(f"/api/projects/{pid}/plans").json()
    assert len(plans) == 1


def test_revise_from_review_unchanged_markdown_is_validation_error(client, app):
    pid = _make_project(client, "prv-same")
    plan_id = _approved_plan(app, pid)
    rid = _review_report(app, pid, plan_id, FINDINGS)

    client.post(f"/api/plans/{plan_id}/revise-from-review", json={"review_id": rid})
    llm = FakeLLM([tool_call("write_plan", {"markdown": SAMPLE})])
    _run_queue(app, llm, profile="plan_revise")

    job = client.get("/api/jobs/1").json()
    assert job["status"] == "failed"
    assert job["error_class"] == "validation"  # 결정론 판정 — 변경 없음
    plans = client.get(f"/api/projects/{pid}/plans").json()
    assert len(plans) == 1