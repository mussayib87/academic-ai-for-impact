"""add support plan versions

Revision ID: bb2233445566
Revises: aa1122334455
Create Date: 2026-10-02 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'bb2233445566'
down_revision: Union[str, None] = 'aa1122334455'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'outcome' not in {column['name'] for column in inspector.get_columns('support_actions')}:
        op.add_column('support_actions', sa.Column('outcome', sa.String(length=200), nullable=True))
    if 'completed_at' not in {column['name'] for column in inspector.get_columns('support_actions')}:
        op.add_column('support_actions', sa.Column('completed_at', sa.DateTime(), nullable=True))
    if 'completed_at' not in {column['name'] for column in inspector.get_columns('support_follow_ups')}:
        op.add_column('support_follow_ups', sa.Column('completed_at', sa.DateTime(), nullable=True))

    op.create_table(
        'support_plan_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('plan_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['teacher_id'], ['teachers.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_support_plan_versions_student_id'), 'support_plan_versions', ['student_id'], unique=False)
    op.create_index(op.f('ix_support_plan_versions_teacher_id'), 'support_plan_versions', ['teacher_id'], unique=False)
    op.create_index(op.f('ix_support_plan_versions_version'), 'support_plan_versions', ['version'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_support_plan_versions_version'), table_name='support_plan_versions')
    op.drop_index(op.f('ix_support_plan_versions_teacher_id'), table_name='support_plan_versions')
    op.drop_index(op.f('ix_support_plan_versions_student_id'), table_name='support_plan_versions')
    op.drop_table('support_plan_versions')

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    action_columns = {column['name'] for column in inspector.get_columns('support_actions')}
    if {'outcome', 'completed_at'} & action_columns:
        with op.batch_alter_table('support_actions') as batch_op:
            if 'completed_at' in action_columns:
                batch_op.drop_column('completed_at')
            if 'outcome' in action_columns:
                batch_op.drop_column('outcome')
    if 'completed_at' in {column['name'] for column in inspector.get_columns('support_follow_ups')}:
        with op.batch_alter_table('support_follow_ups') as batch_op:
            batch_op.drop_column('completed_at')