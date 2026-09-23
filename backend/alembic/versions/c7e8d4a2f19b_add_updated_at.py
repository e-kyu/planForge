"""add updated_at

Revision ID: c7e8d4a2f19b
Revises: 663e20e95505
Create Date: 2026-09-23

가이드 §5.3 공통 컬럼 — 갱신 시각. nullable ADD COLUMN은 SQLite 제약 회피
(상수 기본값 없이 추가 가능하며, 기존 행은 NULL = 아직 갱신되지 않음).
애플리케이션 쪽은 shared/types.py UpdatedAtMixin(onupdate=func.now())이
UPDATE 시 SQL 시간을 기록한다 — 서버 기본값이 필요 없는 이유.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7e8d4a2f19b'
down_revision: Union[str, None] = '663e20e95505'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# §5.3 — 전 테이블 공통 컬럼. 추적성 사슬(projects → review_reports) 전체에 적용.
TABLES = (
    'projects', 'interview_sessions', 'interview_messages', 'facts',
    'plans', 'derivatives', 'builds', 'jobs', 'review_reports',
)


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    # SQLite는 DROP COLUMN을 batch 재작성으로만 수행한다 (env.py render_as_batch와 무관하게
    # 명시 batch — 이 마이그레이션 단독 실행 시에도 안전).
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_column('updated_at')