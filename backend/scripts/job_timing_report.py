# -*- coding: utf-8 -*-
"""잡 타이밍 리포트 — 큐 대기·실행 소요·attempts를 잡별로 요약 (호환 shim).

실행: backend/에서 `python scripts/job_timing_report.py`
DB는 환경변수 DATABASE_URL (미지정 시 루트 data/planforge.db)을 읽기 전용으로 연다.
derive 지연 원인 판별(큐 대기 vs LLM 실행 vs 재시도)에 쓴다 — data/** 쓰기 없음.

본체는 `scripts/admin.py`의 `job-timing` 서브커맨드다 — 기존 실행 경로만 유지한다.
"""
from __future__ import annotations

import sys

from admin import main as _admin_main


def main() -> int:
    return _admin_main(["job-timing"])


if __name__ == "__main__":
    sys.exit(main())
