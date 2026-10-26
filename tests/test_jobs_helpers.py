# -*- coding: utf-8 -*-
"""app/shared·jobs 헬퍼 잠금 테스트 (step 5 — app-shared-helpers).

- enqueue_accepted: 202 가시성(반환 전 커밋) 계약.
- report_progress_safe: DB 오류 삼킴 + 기존 로그 태그·문구 보존.
- latest_by_key: key별 첫 행 채택(정렬은 호출자 소관).
- format_fact_line: 기본/마커/불릿/문자열 날짜 4변형.
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

from _helpers import make_project, make_session
from app.modules.jobs.facade import JobType, enqueue, report_progress_safe
from app.shared.collections import latest_by_key
from app.shared.factline import format_fact_line


def test_enqueue_accepted_commits_before_return(client, app):
    """반환된 JobOut이 이미 커밋돼 다른 세션에서 보인다 — 202 가시성 계약."""
    from app.modules.jobs.infrastructure.models import Job, JobStatus
    from app.modules.jobs.presentation.responses import enqueue_accepted

    pid = make_project(client, "helpers-enqueue")
    with make_session(app) as db:
        out = enqueue_accepted(db, pid, JobType.DERIVE_BUILD,
                               {"plan_id": 1, "kind": "report"})
    assert out.type == "derive_build"
    assert out.status == "queued"
    assert out.payload == {"plan_id": 1, "kind": "report"}

    with make_session(app) as db:
        job = db.get(Job, out.id)
        assert job is not None
        assert job.status == JobStatus.QUEUED


def test_report_progress_safe_swallows_db_error_and_logs_tag(capsys):
    """DB 커밋 실패를 삼키고 기존 문구 그대로 로그를 남긴다 (작업은 계속)."""
    class _BoomDB:
        def commit(self):
            raise RuntimeError("db down")

    job = SimpleNamespace(id=7)
    report_progress_safe(_BoomDB(), job, "llm", log_tag="derive")
    captured = capsys.readouterr()
    assert captured.out.strip() == "[derive] job #7 진행 기록 실패"


def test_report_progress_safe_passes_kwargs(client, app):
    """정상 경로 — step·attempt·detail이 그대로 progress에 기록된다."""
    pid = make_project(client, "helpers-progress")
    with make_session(app) as db:
        job = enqueue(db, pid, JobType.REVIEW, {})
        db.commit()
        report_progress_safe(db, job, "llm", log_tag="review",
                             attempt=2, max_attempts=3, detail="검수 중")
        assert job.progress["step"] == "llm"
        assert job.progress["attempt"] == 2
        assert job.progress["max_attempts"] == 3
        assert job.progress["detail"] == "검수 중"


def test_latest_by_key_first_row_wins_and_keeps_order():
    rows = [{"k": "a", "v": 3}, {"k": "b", "v": 2}, {"k": "a", "v": 1}]
    out = latest_by_key(rows, lambda r: r["k"])
    assert out["a"]["v"] == 3  # 첫 행 채택 (뒤 행이 이기지 않는다)
    assert out["b"]["v"] == 2
    assert list(out) == ["a", "b"]  # 입력 순서 유지


def test_format_fact_line_default():
    assert format_fact_line(date(2026, 10, 1), "매출 4억", "인터뷰") == \
        "[2026-10-01] 매출 4억 (출처: 인터뷰)"


def test_format_fact_line_marker():
    assert format_fact_line(date(2026, 10, 1), "매출 4억", "인터뷰",
                            marker="(미확정)") == \
        "[2026-10-01] 매출 4억 (출처: 인터뷰) (미확정)"


def test_format_fact_line_bullet():
    assert format_fact_line(date(2026, 10, 1), "매출 4억", "인터뷰",
                            bullet=True) == \
        "- [2026-10-01] 매출 4억 (출처: 인터뷰)"


def test_format_fact_line_string_date_and_datetime():
    # 문자열 날짜는 그대로, datetime은 isoformat()
    assert format_fact_line("2026-10-01", "매출 4억", "인터뷰") == \
        "[2026-10-01] 매출 4억 (출처: 인터뷰)"
    assert format_fact_line(datetime(2026, 10, 1, 9, 30), "매출 4억", "인터뷰") == \
        "[2026-10-01T09:30:00] 매출 4억 (출처: 인터뷰)"
