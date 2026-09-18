# -*- coding: utf-8 -*-
"""인터뷰 세션/메시지 API + 팩트 API 테스트 (PR-3 전송 계층)."""
from __future__ import annotations


def _make_project(client) -> int:
    client.post("/api/projects", json={"slug": "fact-demo", "title": "팩트"})
    return 1


def test_create_session_starts_hypothesis(client):
    pid = _make_project(client)
    r = client.post(f"/api/projects/{pid}/interview/sessions", json={})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["phase"] == "hypothesis"
    assert body["round_no"] == 0 and body["status"] == "active"
    assert body["pending_questions"] is None


def test_session_404(client):
    assert client.get("/api/interview/sessions/999").status_code == 404


def test_messages_after_cursor_replay(client):
    pid = _make_project(client)
    client.post(f"/api/projects/{pid}/interview/sessions", json={})
    # 이력 행을 직접 적립해 커서 리플레이를 검증한다 (에이전트는 PR-4에서 연결)
    from app.transcript import append_message
    from app.db import make_session_factory
    from app.main import create_app  # noqa: F401 — app fixture와 동일 엔진 사용

    from app.models import MessageKind, MessageRole

    # client.app의 설정으로 세션 팩토리 생성
    sf = _session_factory(client)
    with sf() as s:
        for i in range(1, 4):
            append_message(s, 1, MessageRole.ASSISTANT, MessageKind.TEXT, f"m{i}")
        s.commit()
    r = client.get("/api/interview/sessions/1/messages")
    assert [m["seq"] for m in r.json()] == [1, 2, 3]
    r = client.get("/api/interview/sessions/1/messages?after=2")
    assert [m["seq"] for m in r.json()] == [3]
    assert r.json()[0]["content"] == "m3"


def _session_factory(client):
    from app.db import make_session_factory

    return make_session_factory(client.app.state.settings.database_url)


def test_facts_crud_and_filter(client):
    pid = _make_project(client)
    r = client.post(f"/api/projects/{pid}/facts",
                    json={"content": "보고 작성 주 10시간", "source": "인터뷰"})
    assert r.status_code == 201
    assert r.json()["origin"] == "manual"
    client.post(f"/api/projects/{pid}/facts", json={"content": "예산 5천만원"})

    r = client.get(f"/api/projects/{pid}/facts")
    assert len(r.json()) == 2
    r = client.get(f"/api/projects/{pid}/facts?status=archived")
    assert r.json() == []

    fid = client.get(f"/api/projects/{pid}/facts").json()[0]["id"]
    r = client.patch(f"/api/projects/{pid}/facts/{fid}", json={"status": "archived"})
    assert r.json()["status"] == "archived"
    r = client.get(f"/api/projects/{pid}/facts?status=archived")
    assert len(r.json()) == 1


def test_fact_404_on_other_project(client):
    _make_project(client)
    client.post("/api/projects", json={"slug": "other", "title": "x"})
    client.post("/api/projects/1/facts", json={"content": "x"})
    # project_id 불일치 → 404 (fact가 다른 프로젝트 소유)
    r = client.patch("/api/projects/2/facts/1", json={"status": "archived"})
    assert r.status_code == 404
    r = client.get("/api/projects/2/facts")
    assert r.json() == []