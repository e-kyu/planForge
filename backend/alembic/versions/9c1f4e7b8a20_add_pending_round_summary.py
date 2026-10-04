"""add pending_round_summary

Revision ID: 9c1f4e7b8a20
Revises: e5f1a9b3c7d4
Create Date: 2026-10-03

인터뷰 라운드 목표(round_summary)의 세션 영속 — _ask_questions가 ask_questions 인자의
round_summary를 정규화해 세션에 적립하고 SessionOut으로 노출한다(카드 부제 표시용).
null은 미제시 상태(구세션·세션 생성 직후). 이력 questions EVENT 행 payload에도
summary가 실리므로 재접속 리플레이에서 라운드 목표가 보존된다. nullable ADD COLUMN은
SQLite 제약 회피 (c7e8d4a2f19b 선례 패턴).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9c1f4e7b8a20'
down_revision: Union[str, None] = 'e5f1a9b3c7d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('interview_sessions',
                  sa.Column('pending_round_summary', sa.Text(), nullable=True))


def downgrade() -> None:
    # SQLite는 DROP COLUMN을 batch 재작성으로만 수행한다 (e5f1a9b3c7d4 선례).
    with op.batch_alter_table('interview_sessions') as batch:
        batch.drop_column('pending_round_summary')