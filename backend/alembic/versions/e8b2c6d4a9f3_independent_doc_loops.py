"""independent doc loops

Revision ID: e8b2c6d4a9f3
Revises: b7c4d9e2f6a1
Create Date: 2026-10-13

문서 3종 독립 진행 (ADR 결정 22 변경 — independent-doc-loops). 컬럼 추가/삭제는
없다: (1) 잔여 locked 행을 active로 전환(데이터 전환), (2) status server_default를
'active'로 교정(신규 시드 규약 반영). downgrade는 이전 순차 시드 규약을 근사 복원한다
(doc_slug != 'proposal' → locked) — active↔done 이력은 복원 대상이 아니다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e8b2c6d4a9f3'
down_revision: Union[str, None] = 'b7c4d9e2f6a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE doc_loops SET status = 'active' WHERE status = 'locked'")
    with op.batch_alter_table('doc_loops') as batch:
        batch.alter_column('status', existing_type=sa.String(length=16),
                           server_default='active', existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('doc_loops') as batch:
        batch.alter_column('status', existing_type=sa.String(length=16),
                           server_default='locked', existing_nullable=False)
    op.execute(
        "UPDATE doc_loops SET status = 'locked' "
        "WHERE status = 'active' AND doc_slug != 'proposal'")