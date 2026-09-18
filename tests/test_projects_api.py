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


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}