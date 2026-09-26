# -*- coding: utf-8 -*-
"""팩트 압축 테스트 (FR-6.1, compact-log 이식) — LLM 그룹 제안 + 결정론 적용 게이트."""
from __future__ import annotations

from pathlib import Path

from fakes import FakeLLM, tool_call

from app.modules.facts.application.compact import build_context, run_llm_compact

PROPOSAL = {
    "summary": "매출 항목 3건이 중복된다",
    "groups": [
        {"topic": "4분기 목표 매출", "keep_id": 3, "archive_ids": [1, 2],
         "reason": "#3이 최종 확정값"},
    ],
}


def _project(client) -> int:
    r = client.post("/api/projects", json={"slug": "compact-t", "title": "x"})
    assert r.status_code == 201
    return r.json()["id"]


def _fact(client, pid: int, content: str, source: str = "사내 집계") -> int:
    r = client.post(f"/api/projects/{pid}/facts", json={"content": content, "source": source})
    assert r.status_code == 201
    return r.json()["id"]


# ---------------------------------------------------------------- LLM 제안 엔진

def test_run_llm_compact_tool_call():
    llm = FakeLLM([tool_call("propose_compact", PROPOSAL)])
    groups, summary, ok = run_llm_compact(llm, [{"id": 1, "date": "2026-09-18",
                                                 "content": "매출 12억", "source": "s"}])
    assert ok and summary == PROPOSAL["summary"] and groups == PROPOSAL["groups"]
    assert "#1" in build_context([{"id": 1, "date": "2026-09-18", "content": "매출 12억",
                                   "source": "s"}])


def test_run_llm_compact_failure_is_lossless():
    llm = FakeLLM([{"content": "도구 없이 텍스트", "tool_calls": []}] * 2)
    groups, summary, ok = run_llm_compact(llm, [])
    assert not ok and groups == []


# ---------------------------------------------------------------- API 게이트

def _seed(client) -> tuple[int, dict]:
    pid = _project(client)
    ids = {
        "old1": _fact(client, pid, "3분기 매출 12.4억 원 (임시 추산)"),
        "old2": _fact(client, pid, "3분기 매출 12.4억 원 (부서별 합산)"),
        "final": _fact(client, pid, "3분기 매출 12.4억 원 (확정)"),
        "unconf": _fact(client, pid, "4분기 목표 15.0억 원 (미확정)"),
        "solo": _fact(client, pid, "고객 47개사"),
    }
    return pid, ids


def test_compact_preview_filters_invalid_and_unconfirmed(client, app):
    pid, ids = _seed(client)
    llm = FakeLLM([tool_call("propose_compact", {
        "summary": "중복 발견",
        "groups": [
            {"topic": "매출", "keep_id": ids["final"],
             "archive_ids": [ids["old1"], ids["old2"], ids["unconf"], 999, 999]},
            {"topic": "나쁜 그룹", "keep_id": 999, "archive_ids": [ids["solo"]]},
            {"topic": "빈 그룹", "keep_id": ids["solo"], "archive_ids": []},
        ],
    })])
    app.state.llm_overrides = {"derive": llm}
    r = client.post(f"/api/projects/{pid}/facts/compact")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True and len(out["groups"]) == 1
    g = out["groups"][0]
    assert g["keep_id"] == ids["final"]
    # (미확정)·미존재 id는 결정론 강제로 제거, keep만 남은 그룹은 제외
    assert g["archive_ids"] == [ids["old1"], ids["old2"]]


def test_compact_preview_llm_failure_is_lossless(client, app):
    pid, _ = _seed(client)
    app.state.llm_overrides = {"derive": FakeLLM([{"content": "?", "tool_calls": []}] * 2)}
    r = client.post(f"/api/projects/{pid}/facts/compact")
    out = r.json()
    assert out["ok"] is False and out["warning"] and out["groups"] == []
    facts = client.get(f"/api/projects/{pid}/facts").json()
    assert len(facts) == 5 and all(f["status"] == "active" for f in facts)


def test_compact_preview_needs_two_facts(client):
    pid = _project(client)
    _fact(client, pid, "단일 팩트")
    out = client.post(f"/api/projects/{pid}/facts/compact").json()
    assert out["ok"] is True and out["groups"] == []


def test_compact_apply_archives_and_rewrites_mirror(client, app, db_env):
    pid, ids = _seed(client)
    body = {"groups": [{"topic": "매출", "keep_id": ids["final"],
                        "archive_ids": [ids["old1"], ids["old2"], ids["unconf"]]}]}
    r = client.post(f"/api/projects/{pid}/facts/compact/apply", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["archived"] == [ids["old1"], ids["old2"]]
    # (미확정) 항목은 활성 유지 + 경고
    assert any("미확정" in w for w in out["warnings"])
    assert out["active_remaining"] == 3

    facts = {f["id"]: f for f in client.get(f"/api/projects/{pid}/facts").json()}
    assert facts[ids["old1"]]["status"] == "archived"
    assert facts[ids["old2"]]["status"] == "archived"
    assert facts[ids["final"]]["status"] == "active"
    assert facts[ids["unconf"]]["status"] == "active"

    # 미러: 활성 로그는 남은 활성만, archive 파일은 이동 항목 + [archive: ] 표기
    log = Path(out["log_path"]).read_text(encoding="utf-8")
    arch = Path(out["archive_path"]).read_text(encoding="utf-8")
    assert "확정)" in log and "임시 추산" not in log
    assert "참고용으로만 읽는다" in arch
    assert "[archive: " in arch and "임시 추산" in arch and "확정)" not in arch
    # 내용 무결성 — 통합은 이동만, 한 글자도 바꾸지 않는다
    assert "3분기 매출 12.4억 원 (확정)" in log
    assert "3분기 매출 12.4억 원 (임시 추산)" in arch


def test_compact_apply_skips_missing_ids(client, app, db_env):
    pid, ids = _seed(client)
    body = {"groups": [{"topic": "매출", "keep_id": 999,
                        "archive_ids": [ids["old1"], ids["old2"]]}]}
    out = client.post(f"/api/projects/{pid}/facts/compact/apply", json=body).json()
    assert out["archived"] == [] and any("999" in w for w in out["warnings"])
    facts = client.get(f"/api/projects/{pid}/facts").json()
    assert all(f["status"] == "active" for f in facts)