"""add job progress

Revision ID: e5f1a9b3c7d4
Revises: c7e8d4a2f19b
Create Date: 2026-09-26

실행 중 잡의 진행 상태(최신 1건) — 핸들러가 facade.report_progress로 기록하고
프론트가 기존 잡 폴링으로 읽어 상태창에 표시한다. nullable ADD COLUMN은 SQLite
제약 회피 (c7e8d4a2f19b 선례 패턴).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f1a9b3c7d4'
down_revision: Union[str, None] = 'c7e8d4a2f19b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('progress', sa.JSON(), nullable=True))


def downgrade() -> None:
    # SQLite는 DROP COLUMN을 batch 재작성으로만 수행한다 (c7e8d4a2f19b 선례).
    with op.batch_alter_table('jobs') as batch:
        batch.drop_column('progress')