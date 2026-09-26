# -*- coding: utf-8 -*-
"""잡 타이밍 리포트 — 큐 대기·실행 소요·attempts를 잡별로 요약 (읽기 전용).

실행: backend/에서 `python scripts/job_timing_report.py`
DB는 환경변수 DATABASE_URL (미지정 시 루트 data/planforge.db)을 읽기 전용으로 연다.
derive 지연 원인 판별(큐 대기 vs LLM 실행 vs 재시도)에 쓴다 — data/** 쓰기 없음.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def main() -> None:
    from sqlalchemy import create_engine, text

    url = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{(BACKEND_DIR.parent / 'data' / 'planforge.db').as_posix()}",
    )
    engine = create_engine(url)

    rows = engine.execute(text(
        "SELECT id, type, status, attempts, created_at, started_at, finished_at, result "
        "FROM jobs ORDER BY id")).mappings().all()
    if not rows:
        print("잡이 없다.")
        return

    waits: dict[str, list[float]] = {}
    runs: dict[str, list[float]] = {}
    print(f"{'id':>4} {'type':<12} {'status':<8} {'try':>3} "
          f"{'대기s':>7} {'실행s':>7}  attempts(result)")
    for r in rows:
        wait = run = None
        if r["started_at"] and r["created_at"]:
            wait = (r["started_at"] - r["created_at"]).total_seconds()
        if r["finished_at"] and r["started_at"]:
            run = (r["finished_at"] - r["started_at"]).total_seconds()
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


if __name__ == "__main__":
    main()