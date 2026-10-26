# -*- coding: utf-8 -*-
"""앱 인지 관리 CLI — OpenAPI 계약 덤프 + 잡 타이밍 리포트.

실행 (backend/에서):
  python scripts/admin.py openapi       # → frontend/openapi.json
  python scripts/admin.py job-timing    # 잡 큐 대기·실행 소요 요약 (읽기 전용)

기존 경로 `scripts/export_openapi.py`·`scripts/job_timing_report.py`는 이 모듈의
얇은 shim이다. `planforge/`는 웹 비의존 계약이므로 app·DB 인지 코드는 여기에 둔다.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys

from _bootstrap import REPO_ROOT, database_url, ensure_paths

# app·planforge import 경로 (conftest와 동일 규약 — 패키지 src 최우선)
ensure_paths()

# 계약 산출물 경로 — 테스트는 monkeypatch로 대체한다 (실제 계약 파일 보호)
OUT = REPO_ROOT / "frontend" / "openapi.json"


def cmd_openapi(args: argparse.Namespace) -> int:
    """create_app(start_worker=False)의 스키마를 계약 파일에 덤프한다."""
    from app.main import create_app

    app = create_app(start_worker=False)
    schema = app.openapi()
    OUT.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {OUT}")
    return 0


def _dt(v) -> object | None:
    """raw sqlite 조회 값(문자열 또는 datetime) → datetime. naive면 UTC로 간주."""
    import datetime as dt_mod

    if v is None:
        return None
    if isinstance(v, dt_mod.datetime):
        return v
    return dt_mod.datetime.fromisoformat(v)


def cmd_job_timing(args: argparse.Namespace) -> int:
    """큐 대기·실행 소요·attempts를 잡별로 요약한다 (읽기 전용 — data/** 쓰기 없음)."""
    from sqlalchemy import create_engine, text

    url = database_url()
    engine = create_engine(url)

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, type, status, attempts, created_at, started_at, finished_at, result "
            "FROM jobs ORDER BY id")).mappings().all()
    if not rows:
        print("잡이 없다.")
        return 0

    waits: dict[str, list[float]] = {}
    runs: dict[str, list[float]] = {}
    print(f"{'id':>4} {'type':<12} {'status':<8} {'try':>3} "
          f"{'대기s':>7} {'실행s':>7}  attempts(result)")
    for r in rows:
        wait = run = None
        created, started, finished = _dt(r["created_at"]), _dt(r["started_at"]), _dt(r["finished_at"])
        if started and created:
            wait = (started - created).total_seconds()
        if finished and started:
            run = (finished - started).total_seconds()
        att = r["attempts"] or 0
        r_att = ""
        if r["result"]:
            try:
                counts = json.loads(r["result"]).get("counts", {})
                if counts.get("attempts") is not None:
                    r_att = f"LLM attempts={counts['attempts']}"
            except (ValueError, AttributeError):
                pass
        print(f"{r['id']:>4} {r['type']:<12} {r['status']:<8} {att:>3} "
              f"{'-' if wait is None else f'{wait:.0f}':>7} "
              f"{'-' if run is None else f'{run:.0f}':>7}  {r_att}")
        if wait is not None:
            waits.setdefault(r["type"], []).append(wait)
        if run is not None:
            runs.setdefault(r["type"], []).append(run)

    print("\n=== 타입별 요약 (완료/실행된 잡) ===")
    for label, groups in (("큐 대기", waits), ("실행 소요", runs)):
        for t, vals in groups.items():
            med = statistics.median(vals)
            print(f"{label} [{t}] n={len(vals)} 중간값={med:.0f}s 최대={max(vals):.0f}s")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="admin", description="PlanForge 앱 관리 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("openapi", help="OpenAPI 스키마를 frontend/openapi.json에 덤프")
    sp.set_defaults(fn=cmd_openapi)

    sj = sub.add_parser("job-timing", help="잡 타이밍 리포트 (읽기 전용)")
    sj.set_defaults(fn=cmd_job_timing)

    return p


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:  # --help·인자 오류도 종료 코드로 돌려준다
        return int(exc.code or 0)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
