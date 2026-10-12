"""add doc_loops

Revision ID: b7c4d9e2f6a1
Revises: 9c1f4e7b8a20
Create Date: 2026-10-13

카드별 산출물 선순환 루프 (Phase 1 — 스키마 확립). 문서별 루프 상태 테이블
doc_loops와 문서 정체성 doc_slug의 nullable 부착(plans · interview_sessions ·
builds). doc_slug NULL = 레거시(문서 루프 도입 전 · 워크스페이스 루트 경로) —
데이터 마이그레이션은 의도적으로 없다. nullable ADD COLUMN은 SQLite 제약 회피
(9c1f4e7b8a20 · c7e8d4a2f19b 선례 패턴).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c4d9e2f6a1'
down_revision: Union[str, None] = '9c1f4e7b8a20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'doc_loops',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('doc_slug', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='locked', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'doc_slug', name='uq_project_docloop')
    )
    op.create_index(op.f('ix_doc_loops_project_id'), 'doc_loops', ['project_id'], unique=False)
    for table in ('plans', 'interview_sessions', 'builds'):
        op.add_column(table, sa.Column('doc_slug', sa.String(length=32), nullable=True))


def downgrade() -> None:
    for table in ('plans', 'interview_sessions', 'builds'):
        with op.batch_alter_table(table) as batch:
            batch.drop_column('doc_slug')
    op.drop_index(op.f('ix_doc_loops_project_id'), table_name='doc_loops')
    op.drop_table('doc_loops')