# -*- coding: utf-8 -*-
"""소스 API (FR-2.1 + §5 업로드 검증) 테스트."""
from __future__ import annotations

from urllib.parse import unquote

from app.shared.workspace import read_sources_context

from _helpers import make_project

OVERVIEW = "overview.md"  # shared.workspace.OVERVIEW_NAME — 하드코딩으로 계약 고정


def test_upload_list_delete_source(client, db_env):
    pid = make_project(client, "src-demo", "소스 데모")
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
    pid = make_project(client, "src-demo", "소스 데모")
    for fname in ("악성.exe", "스크립트.js", "그림.png", "확장자없음"):
        r = client.post(f"/api/projects/{pid}/sources",
                        files={"file": (fname, b"x", "application/octet-stream")})
        assert r.status_code == 409, fname


def test_upload_rejects_oversize_and_non_utf8(client):
    pid = make_project(client, "src-demo", "소스 데모")
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
    pid = make_project(client, "src-demo", "소스 데모")
    data = b"# v1"
    client.post(f"/api/projects/{pid}/sources",
                files={"file": ("요구.md", data, "text/markdown")})
    r = client.post(f"/api/projects/{pid}/sources",
                    files={"file": ("요구.md", b"# v2", "text/markdown")})
    assert r.status_code == 409
    # 파일이 변하지 않는다 (무덮어쓰기)
    assert (db_env / "src-demo" / "sources" / "요구.md").read_bytes() == data


def test_upload_filename_traversal_and_forbidden_chars_sanitized(client, db_env):
    pid = make_project(client, "src-demo", "소스 데모")
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
    pid = make_project(client, "src-demo", "소스 데모")
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


# ---------------------------------------------------------------- 개요 문서 (sources/overview.md)

def _overview_path(db_env, slug="src-demo"):
    return db_env / slug / "sources" / OVERVIEW


def test_overview_missing_returns_empty(client, db_env):
    pid = make_project(client, "src-demo", "소스 데모")
    r = client.get(f"/api/projects/{pid}/overview")
    assert r.status_code == 200, r.text
    assert r.json() == {"exists": False, "content": "", "size": 0, "mtime": None}
    # 부재 조회로 파일은 만들어지지 않는다
    assert not _overview_path(db_env).exists()


def test_overview_put_creates_lf_no_bom(client, db_env):
    pid = make_project(client, "src-demo", "소스 데모")
    r = client.put(f"/api/projects/{pid}/overview", json={"content": "# 프로젝트 개요\n\n## 목적"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["exists"] is True
    raw = _overview_path(db_env).read_bytes()
    assert raw == "# 프로젝트 개요\n\n## 목적".encode("utf-8")
    assert b"\r\n" not in raw  # 개행 LF 고정
    assert not raw.startswith(b"\xef\xbb\xbf")  # BOM 없음


def test_overview_put_overwrites_and_normalizes_newlines(client, db_env):
    pid = make_project(client, "src-demo", "소스 데모")
    r1 = client.put(f"/api/projects/{pid}/overview", json={"content": "# v1"})
    assert r1.status_code == 200, r1.text
    # 소스 업로드의 409-무덮어쓰기와 달리 개요는 업서트가 유일한 쓰기 경로
    r2 = client.put(f"/api/projects/{pid}/overview", json={"content": "# v2\r\n본문\r텍스트"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["content"] == "# v2\n본문\n텍스트"
    assert _overview_path(db_env).read_text(encoding="utf-8") == "# v2\n본문\n텍스트"


def test_overview_get_roundtrip(client, db_env):
    pid = make_project(client, "src-demo", "소스 데모")
    content = "# 프로젝트 개요\n\n인터뷰 기본자료"
    client.put(f"/api/projects/{pid}/overview", json={"content": content})
    r = client.get(f"/api/projects/{pid}/overview")
    body = r.json()
    assert body["exists"] is True
    assert body["content"] == content
    assert body["size"] == len(content.encode("utf-8"))
    assert isinstance(body["mtime"], float)


def test_overview_put_rejects_empty(client, db_env):
    pid = make_project(client, "src-demo", "소스 데모")
    for content in ("", "   \n  "):
        r = client.put(f"/api/projects/{pid}/overview", json={"content": content})
        assert r.status_code == 409
        assert "비어" in r.json()["detail"]
    assert not _overview_path(db_env).exists()  # 첫 저장 차단 — 빈 파일 방치 방지


def test_overview_put_rejects_oversize(client):
    pid = make_project(client, "src-demo", "소스 데모")
    r = client.put(f"/api/projects/{pid}/overview",
                   json={"content": "a" * (2 * 1024 * 1024 + 1)})
    assert r.status_code == 409
    assert "너무 큽니다" in r.json()["detail"]


def test_overview_unknown_project_404(client):
    r = client.get("/api/projects/9999/overview")
    assert r.status_code == 404
    r = client.put("/api/projects/9999/overview", json={"content": "# x"})
    assert r.status_code == 404


# ---------------------------------------------------------------- 소스 다운로드 (DELETE와 대칭)

def test_source_download_roundtrip(client, db_env):
    pid = make_project(client, "src-demo", "소스 데모")
    client.put(f"/api/projects/{pid}/overview", json={"content": "# 개요 본문"})
    client.post(f"/api/projects/{pid}/sources",
                files={"file": ("메뉴얼.txt", "일반 소스 본문".encode("utf-8"), "text/plain")})

    r = client.get(f"/api/projects/{pid}/sources/{OVERVIEW}/download")
    assert r.status_code == 200, r.text
    assert r.content == "# 개요 본문".encode("utf-8")
    assert r.headers["content-type"].startswith("text/markdown")
    assert OVERVIEW in r.headers["content-disposition"]

    r = client.get(f"/api/projects/{pid}/sources/메뉴얼.txt/download")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")


def test_source_download_missing_404(client):
    pid = make_project(client, "src-demo", "소스 데모")
    r = client.get(f"/api/projects/{pid}/sources/{OVERVIEW}/download")
    assert r.status_code == 404


def test_source_delete_and_download_reject_traversal(client, db_env):
    pid = make_project(client, "src-demo", "소스 데모")
    plan = db_env / "src-demo" / "plan.md"  # sources/ 밖 — 접근 불가해야 한다
    plan.write_text("# plan", encoding="utf-8")
    # httpx는 URL의 '.' 세그먼트를 클라이언트에서 정규화해 버리므로(앱 미도달),
    # 서버 도착값이 '..'이 되는 인코딩 변형으로 앱의 가드를 직접 검증한다.
    for encoded in ("..%2Fplan.md", "..%5Cplan.md", "%2E%2E"):
        r = client.get(f"/api/projects/{pid}/sources/{encoded}/download")
        assert r.status_code == 404, encoded
        r = client.delete(f"/api/projects/{pid}/sources/{encoded}")
        assert r.status_code == 404, encoded
    assert plan.read_text(encoding="utf-8") == "# plan"


# ---------------------------------------------------------------- 글로벌 소스 다운로드 (읽기 전용)

def test_global_source_download_roundtrip(client, db_env, monkeypatch):
    glob = db_env / "global-sources"
    glob.mkdir(parents=True)
    (glob / "공용-메뉴얼.txt").write_text("공용 소스 본문", encoding="utf-8")
    monkeypatch.setenv("GLOBAL_SOURCES_DIR", str(glob))

    r = client.get("/api/sources/공용-메뉴얼.txt/download")
    assert r.status_code == 200, r.text
    assert r.content == "공용 소스 본문".encode("utf-8")
    assert r.headers["content-type"].startswith("text/plain")
    # 비ASCII 파일명 — RFC 5987 filename*으로 인코딩되어 실린다
    cd = r.headers["content-disposition"]
    assert unquote(cd.split("utf-8''")[1]) == "공용-메뉴얼.txt"
    # 다운로드는 파일을 변하지 않게 한다 — 글로벌 소스는 읽기 전용이다
    assert (glob / "공용-메뉴얼.txt").read_text(encoding="utf-8") == "공용 소스 본문"


def test_global_source_download_missing_and_traversal(client, db_env, monkeypatch):
    glob = db_env / "global-sources"
    glob.mkdir(parents=True)
    (glob / "공용.txt").write_text("x", encoding="utf-8")
    outside = db_env / "outside.md"  # global-sources/ 밖 — 접근 불가해야 한다
    outside.write_text("# outside", encoding="utf-8")
    monkeypatch.setenv("GLOBAL_SOURCES_DIR", str(glob))

    r = client.get("/api/sources/없는파일.txt/download")
    assert r.status_code == 404
    for encoded in ("..%2Foutside.md", "..%5Coutside.md", "%2E%2E"):
        r = client.get(f"/api/sources/{encoded}/download")
        assert r.status_code == 404, encoded
    assert outside.read_text(encoding="utf-8") == "# outside"


def test_overview_in_sources_list_and_interview_context(client, db_env):
    pid = make_project(client, "src-demo", "소스 데모")
    content = "# 프로젝트 개요\n\n인터뷰 기본자료로 활용된다"
    client.put(f"/api/projects/{pid}/overview", json={"content": content})

    r = client.get(f"/api/projects/{pid}/sources")
    assert OVERVIEW in [s["name"] for s in r.json()]  # 일반 소스로 목록 표시

    # 인터뷰 턴의 소스 주입(self.sources_dirs → read_sources_context)에 자동 포함
    ctx = read_sources_context([db_env / "src-demo" / "sources"])
    assert "인터뷰 기본자료로 활용된다" in ctx