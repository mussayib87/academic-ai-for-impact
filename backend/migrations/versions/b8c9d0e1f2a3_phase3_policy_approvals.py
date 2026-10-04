"""record explicit Phase 3 aggregation and feature-contract approvals

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-03 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'phase3_policy_approvals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('aggregation_strategy', sa.String(length=80), nullable=False),
        sa.Column('feature_contract', sa.JSON(), nullable=False),
        sa.Column('approved_by_user_id', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=False),
        sa.Column('approval_note', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['approved_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_phase3_policy_approvals_approved_by_user_id',
        'phase3_policy_approvals',
        ['approved_by_user_id'],
        unique=False,
    )
    if op.get_bind().dialect.name == 'sqlite':
        op.execute("""
            CREATE TRIGGER trg_phase3_policy_approvals_no_update
            BEFORE UPDATE ON phase3_policy_approvals
            BEGIN
                SELECT RAISE(ABORT, 'Phase 3 policy approval records are immutable');
            END
        """)
        op.execute("""
            CREATE TRIGGER trg_phase3_policy_approvals_no_delete
            BEFORE DELETE ON phase3_policy_approvals
            BEGIN
                SELECT RAISE(ABORT, 'Phase 3 policy approval records are immutable');
            END
        """)


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        op.execute('DROP TRIGGER IF EXISTS trg_phase3_policy_approvals_no_delete')
        op.execute('DROP TRIGGER IF EXISTS trg_phase3_policy_approvals_no_update')
    op.drop_index('ix_phase3_policy_approvals_approved_by_user_id', table_name='phase3_policy_approvals')
    op.drop_table('phase3_policy_approvals')
