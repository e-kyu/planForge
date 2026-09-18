"""review_reports table

Revision ID: 663e20e95505
Revises: 22d6dcbe6fee
Create Date: 2026-09-18 17:17:31.725291
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '663e20e95505'
down_revision: Union[str, None] = '22d6dcbe6fee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'review_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('plans.id'), nullable=False, index=True),
        sa.Column('findings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('red_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('yellow_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('white_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('llm_ok', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default='now()'),
    )


def downgrade() -> None:
    op.drop_table('review_reports')