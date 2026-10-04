"""add student support actions and follow-ups

Revision ID: aa1122334455
Revises: f6a7b8c9d0e1
Create Date: 2026-10-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'aa1122334455'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'support_actions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('action_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=40), nullable=False),
        sa.Column('due_date', sa.DateTime(), nullable=True),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['teacher_id'], ['teachers.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_support_actions_student_id'), 'support_actions', ['student_id'], unique=False)
    op.create_index(op.f('ix_support_actions_teacher_id'), 'support_actions', ['teacher_id'], unique=False)
    op.create_index(op.f('ix_support_actions_status'), 'support_actions', ['status'], unique=False)

    op.create_table(
        'support_follow_ups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('assigned_to', sa.String(length=200), nullable=False),
        sa.Column('scheduled_date', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=40), nullable=False),
        sa.Column('outcome', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_support_follow_ups_student_id'), 'support_follow_ups', ['student_id'], unique=False)
    op.create_index(op.f('ix_support_follow_ups_status'), 'support_follow_ups', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_support_follow_ups_status'), table_name='support_follow_ups')
    op.drop_index(op.f('ix_support_follow_ups_student_id'), table_name='support_follow_ups')
    op.drop_table('support_follow_ups')

    op.drop_index(op.f('ix_support_actions_status'), table_name='support_actions')
    op.drop_index(op.f('ix_support_actions_teacher_id'), table_name='support_actions')
    op.drop_index(op.f('ix_support_actions_student_id'), table_name='support_actions')
    op.drop_table('support_actions')
