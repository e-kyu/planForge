# -*- coding: utf-8 -*-
"""소스 API (FR-2.1 + §5 업로드 검증) 테스트."""
from __future__ import annotations


def _mk(client, slug="src-demo"):
    r = client.post("/api/projects", json={"slug": slug, "title": "소스 데모"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_upload_list_delete_source(client, db_env):
    pid = _mk(client)
    r = client.post(f"/api/projects/{pid}/sources",
                    files={"file": ("요구사항.md", "# 요구\n- v2.0".encode("utf-8"),
                                    "text/markdown")})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body == {"name": "요구사항.md", "size": body["size"], "dir": "project",
                    "mtime": body["mtime"]}
    assert (db_env / "src-demo" / "sources" / "요구사항.md").read_bytes() == \
        "# 요구\n- v2.0".encode("utf-8")

    r = client.get(f"/api/projects/{pid}/sources")
    names = [s["name"] for s in r.json()]
    assert names == ["요구사항.md"]

    r = client.delete(f"/api/projects/{pid}/sources/요구사항.md")
    assert r.status_code == 204
    r = client.get(f"/api/projects/{pid}/sources")
    assert r.json() == []


def test_upload_rejects_bad_extension(client):
    pid = _mk(client)
    for fname in ("악성.exe", "스크립트.js", "그림.png", "확장자없음"):
        r = client.post(f"/api/projects/{pid}/sources",
                        files={"file": (fname, b"x", "application/octet-stream")})
        assert r.status_code == 409, fname


def test_upload_rejects_oversize_and_non_utf8(client):
    pid = _mk(client)
    big = b"a" * (2 * 1024 * 1024 + 1)
    r = client.post(f"/api/projects/{pid}/sources",
                    files={"file": ("큰파일.md", big, "text/markdown")})
    assert r.status_code == 409
    assert "너무 큽니다" in r.json()["detail"]

    r = client.post(f"/api/projects/{pid}/sources",
                    files={"file": ("cp949.md", b"\xb1\xdb\xc0\xce", "text/plain")})
    assert r.status_code == 409
    assert "UTF-8" in r.json()["detail"]


def test_upload_duplicate_conflict_and_overwrite_never(client, db_env):
    pid = _mk(client)
    data = b"# v1"
    client.post(f"/api/projects/{pid}/sources",
                files={"file": ("요구.md", data, "text/markdown")})
    r = client.post(f"/api/projects/{pid}/sources",
                    files={"file": ("요구.md", b"# v2", "text/markdown")})
    assert r.status_code == 409
    # 파일이 변하지 않는다 (무덮어쓰기)
    assert (db_env / "src-demo" / "sources" / "요구.md").read_bytes() == data


def test_upload_filename_traversal_and_forbidden_chars_sanitized(client, db_env):
    pid = _mk(client)
    # 경로 성분 제거 — 서버의 다른 디렉토리에 쓰일 수 없다
    r = client.post(f"/api/projects/{pid}/sources",
                    files={"file": ("../../evil.md", b"x", "text/markdown")})
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "evil.md"
    assert not (db_env / "evil.md").exists()

    r = client.post(f"/api/projects/{pid}/sources",
                    files={"file": ("보고:서브*?.md", b"x", "text/markdown")})
    assert r.status_code == 201
    assert r.json()["name"] == "보고_서브__.md"

    # 정규화 후 빈 이름
    r = client.post(f"/api/projects/{pid}/sources",
                    files={"file": ("...", b"x", "text/markdown")})
    assert r.status_code == 409


def test_deleted_source_404_and_unknown_project_404(client):
    pid = _mk(client)
    r = client.delete(f"/api/projects/{pid}/sources/없는파일.md")
    assert r.status_code == 404
    r = client.get("/api/projects/9999/sources")
    assert r.status_code == 404
    r = client.post("/api/projects/9999/sources",
                    files={"file": ("a.md", b"x", "text/markdown")})
    assert r.status_code == 404


def test_global_sources_readonly_listing(client, db_env, monkeypatch):
    glob = db_env / "global-sources"
    glob.mkdir(parents=True)
    (glob / "공용-메뉴얼.txt").write_text("공용 소스", encoding="utf-8")
    monkeypatch.setenv("GLOBAL_SOURCES_DIR", str(glob))
    # get_settings는 환경변수를 매 요청 새로 읽는다 — 캐시 리셋 없이 재구성됨
    r = client.get("/api/sources")
    items = [s for s in r.json() if s["name"] == "공용-메뉴얼.txt"]
    assert len(items) == 1
    assert items[0]["dir"] == "global"
    # 글로벌에는 쓰기/삭제 경로가 없다 — 프로젝트 소스로만 조작 가능
    r = client.delete("/api/sources/공용-메뉴얼.txt")
    assert r.status_code in (404, 405)