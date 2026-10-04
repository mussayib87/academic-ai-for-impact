"""scope subject marks by academic period and retain history

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-01 00:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('student_subject_academic_records') as batch:
        batch.drop_constraint('uq_student_subject_academic_record', type_='unique')
        batch.add_column(sa.Column('academic_period', sa.String(length=30), nullable=False, server_default='UNSPECIFIED'))
        batch.add_column(sa.Column('fa1_observed_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('fa2_observed_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('assignment_observed_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('attendance_observed_at', sa.DateTime(), nullable=True))
        batch.create_index(op.f('ix_student_subject_academic_records_academic_period'), ['academic_period'], unique=False)
        batch.create_unique_constraint('uq_student_subject_period_record', ['student_id', 'subject_id', 'academic_period'])
        batch.alter_column('academic_period', server_default=None)

    with op.batch_alter_table('academic_data_import_rows') as batch:
        batch.add_column(sa.Column('academic_record_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_import_row_academic_record', 'student_subject_academic_records', ['academic_record_id'], ['id'], ondelete='SET NULL')
        batch.create_index(op.f('ix_academic_data_import_rows_academic_record_id'), ['academic_record_id'], unique=False)

    op.create_table(
        'student_subject_academic_record_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('academic_record_id', sa.Integer(), nullable=False),
        sa.Column('import_batch_id', sa.Integer(), nullable=True),
        sa.Column('changed_by_user_id', sa.Integer(), nullable=True),
        sa.Column('change_kind', sa.String(length=20), nullable=False),
        sa.Column('fa1', sa.Float(), nullable=True),
        sa.Column('fa1_observed_at', sa.DateTime(), nullable=True),
        sa.Column('fa2', sa.Float(), nullable=True),
        sa.Column('fa2_observed_at', sa.DateTime(), nullable=True),
        sa.Column('assignment_mark', sa.Float(), nullable=True),
        sa.Column('assignment_observed_at', sa.DateTime(), nullable=True),
        sa.Column('attendance_rate', sa.Float(), nullable=True),
        sa.Column('attendance_observed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['academic_record_id'], ['student_subject_academic_records.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['import_batch_id'], ['academic_data_import_batches.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['changed_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_student_subject_academic_record_history_academic_record_id'), 'student_subject_academic_record_history', ['academic_record_id'], unique=False)
    op.create_index(op.f('ix_student_subject_academic_record_history_import_batch_id'), 'student_subject_academic_record_history', ['import_batch_id'], unique=False)
    op.create_index(op.f('ix_student_subject_academic_record_history_changed_by_user_id'), 'student_subject_academic_record_history', ['changed_by_user_id'], unique=False)

    op.create_table(
        'academic_risk_outcomes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('academic_period', sa.String(length=30), nullable=False),
        sa.Column('risk_level', sa.String(length=20), nullable=False),
        sa.Column('observed_at', sa.DateTime(), nullable=False),
        sa.Column('outcome_source', sa.String(length=255), nullable=False),
        sa.Column('import_batch_id', sa.Integer(), nullable=True),
        sa.Column('recorded_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['import_batch_id'], ['academic_data_import_batches.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['recorded_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('student_id', 'academic_period', name='uq_student_academic_period_risk_outcome'),
    )
    op.create_index(op.f('ix_academic_risk_outcomes_student_id'), 'academic_risk_outcomes', ['student_id'], unique=False)
    op.create_index(op.f('ix_academic_risk_outcomes_academic_period'), 'academic_risk_outcomes', ['academic_period'], unique=False)
    op.create_index(op.f('ix_academic_risk_outcomes_observed_at'), 'academic_risk_outcomes', ['observed_at'], unique=False)
    op.create_index(op.f('ix_academic_risk_outcomes_import_batch_id'), 'academic_risk_outcomes', ['import_batch_id'], unique=False)
    op.create_index(op.f('ix_academic_risk_outcomes_recorded_by_user_id'), 'academic_risk_outcomes', ['recorded_by_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_academic_risk_outcomes_recorded_by_user_id'), table_name='academic_risk_outcomes')
    op.drop_index(op.f('ix_academic_risk_outcomes_import_batch_id'), table_name='academic_risk_outcomes')
    op.drop_index(op.f('ix_academic_risk_outcomes_observed_at'), table_name='academic_risk_outcomes')
    op.drop_index(op.f('ix_academic_risk_outcomes_academic_period'), table_name='academic_risk_outcomes')
    op.drop_index(op.f('ix_academic_risk_outcomes_student_id'), table_name='academic_risk_outcomes')
    op.drop_table('academic_risk_outcomes')
    op.drop_index(op.f('ix_student_subject_academic_record_history_changed_by_user_id'), table_name='student_subject_academic_record_history')
    op.drop_index(op.f('ix_student_subject_academic_record_history_import_batch_id'), table_name='student_subject_academic_record_history')
    op.drop_index(op.f('ix_student_subject_academic_record_history_academic_record_id'), table_name='student_subject_academic_record_history')
    op.drop_table('student_subject_academic_record_history')
    with op.batch_alter_table('academic_data_import_rows') as batch:
        batch.drop_index(op.f('ix_academic_data_import_rows_academic_record_id'))
        batch.drop_constraint('fk_import_row_academic_record', type_='foreignkey')
        batch.drop_column('academic_record_id')
    with op.batch_alter_table('student_subject_academic_records') as batch:
        batch.drop_constraint('uq_student_subject_period_record', type_='unique')
        batch.drop_index(op.f('ix_student_subject_academic_records_academic_period'))
        batch.drop_column('attendance_observed_at')
        batch.drop_column('assignment_observed_at')
        batch.drop_column('fa2_observed_at')
        batch.drop_column('fa1_observed_at')
        batch.drop_column('academic_period')
        batch.create_unique_constraint('uq_student_subject_academic_record', ['student_id', 'subject_id'])