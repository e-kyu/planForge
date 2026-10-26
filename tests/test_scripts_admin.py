# -*- coding: utf-8 -*-
"""앱 관리 CLI(`backend/scripts/admin.py`) 테스트 — 부트스트랩·DB URL·shim 계약.

`backend/scripts`는 패키지가 아니므로 이 모듈이 먼저 sys.path에 올린 뒤 import한다.
OpenAPI 서브커맨드는 create_app·출력 경로를 monkeypatch로 대체해 실제 계약 파일
(`frontend/openapi.json`)을 건드리지 않는다.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "backend" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import _bootstrap  # noqa: E402
import admin  # noqa: E402


def test_ensure_paths_makes_app_and_planforge_importable():
    _bootstrap.ensure_paths()

    import app
    import planforge

    assert Path(app.__file__).resolve().is_relative_to(_bootstrap.BACKEND_DIR)
    assert Path(planforge.__file__).resolve().is_relative_to(_bootstrap.PACKAGE_SRC)


def test_database_url_honours_env(monkeypatch, tmp_path):
    url = f"sqlite:///{(tmp_path / 'override.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    assert _bootstrap.database_url() == url


def test_admin_help_returns_zero(capsys):
    assert admin.main(["--help"]) == 0
    assert "usage: admin" in capsys.readouterr().out


@pytest.mark.parametrize("name", ["export_openapi", "job_timing_report"])
def test_legacy_shims_expose_main(name):
    path = SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_shim_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert callable(mod.main)


def test_openapi_writes_schema_with_injected_app(monkeypatch, tmp_path, capsys):
    """create_app·출력 경로를 대체 — 실제 계약 파일은 덮어쓰지 않는다."""
    schema = {"info": {"title": "가짜 계약"}, "paths": {}}
    calls: dict[str, object] = {}

    class FakeApp:
        def openapi(self):
            return schema

    def fake_create_app(*, start_worker=True, llm_overrides=None):
        calls["start_worker"] = start_worker
        return FakeApp()

    out = tmp_path / "openapi.json"
    monkeypatch.setattr(admin, "OUT", out)
    monkeypatch.setattr("app.main.create_app", fake_create_app)

    assert admin.main(["openapi"]) == 0

    assert calls == {"start_worker": False}
    assert out.read_text(encoding="utf-8") == json.dumps(schema, ensure_ascii=False, indent=2)
    assert f"written: {out}" in capsys.readouterr().out


def test_job_timing_on_empty_db_prints_message(monkeypatch, tmp_path, capsys):
    import sqlalchemy as sa

    url = f"sqlite:///{(tmp_path / 'jobs.db').as_posix()}"
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(sa.text(
                "CREATE TABLE jobs (id INTEGER PRIMARY KEY, type TEXT, status TEXT, "
                "attempts INTEGER, created_at TEXT, started_at TEXT, finished_at TEXT, result TEXT)"))
    finally:
        engine.dispose()
    monkeypatch.setenv("DATABASE_URL", url)

    assert admin.main(["job-timing"]) == 0
    assert "잡이 없다." in capsys.readouterr().out
