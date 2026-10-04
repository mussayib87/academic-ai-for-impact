"""add subject-aware academic records

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-01 00:00:00.000000
"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SUBJECTS = (
    ('EVS', 'Environmental Studies'),
    ('CN', 'Computer Networks'),
    ('TOC', 'Theory of Computation'),
    ('RM', 'Research Methodology'),
    ('SE', 'Software Engineering'),
)


def upgrade() -> None:
    with op.batch_alter_table('submission_versions') as batch:
        batch.add_column(sa.Column('page_number', sa.Integer(), nullable=False, server_default='1'))
        batch.add_column(sa.Column('page_count', sa.Integer(), nullable=False, server_default='1'))
    with op.batch_alter_table('submissions') as batch:
        batch.add_column(sa.Column('page_count', sa.Integer(), nullable=False, server_default='1'))
    with op.batch_alter_table('assignments') as batch:
        batch.add_column(sa.Column('subject_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_assignments_subject_id_subjects', 'subjects', ['subject_id'], ['id'], ondelete='SET NULL')
        batch.create_index(op.f('ix_assignments_subject_id'), ['subject_id'], unique=False)
    op.create_table(
        'student_subject_academic_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
        sa.Column('fa1', sa.Float(), nullable=True),
        sa.Column('fa2', sa.Float(), nullable=True),
        sa.Column('assignment_mark', sa.Float(), nullable=True),
        sa.Column('attendance_rate', sa.Float(), nullable=True),
        sa.Column('import_batch_id', sa.Integer(), nullable=True),
        sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['import_batch_id'], ['academic_data_import_batches.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('student_id', 'subject_id', name='uq_student_subject_academic_record'),
    )
    op.create_index(op.f('ix_student_subject_academic_records_student_id'), 'student_subject_academic_records', ['student_id'], unique=False)
    op.create_index(op.f('ix_student_subject_academic_records_subject_id'), 'student_subject_academic_records', ['subject_id'], unique=False)
    op.create_index(op.f('ix_student_subject_academic_records_import_batch_id'), 'student_subject_academic_records', ['import_batch_id'], unique=False)
    op.create_index(op.f('ix_student_subject_academic_records_updated_by_user_id'), 'student_subject_academic_records', ['updated_by_user_id'], unique=False)

    subjects = sa.table(
        'subjects',
        sa.column('name', sa.String),
        sa.column('code', sa.String),
        sa.column('department', sa.String),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
    )
    bind = op.get_bind()
    for code, name in SUBJECTS:
        if bind.execute(sa.select(subjects.c.code).where(subjects.c.code == code)).first() is None:
            now = datetime.utcnow()
            bind.execute(subjects.insert().values(name=name, code=code, department='', created_at=now, updated_at=now))
    bind.execute(sa.text('UPDATE assignments SET subject_id = (SELECT id FROM subjects WHERE subjects.name = assignments.subject OR subjects.code = assignments.subject LIMIT 1) WHERE subject_id IS NULL'))


def downgrade() -> None:
    with op.batch_alter_table('submissions') as batch:
        batch.drop_column('page_count')
    with op.batch_alter_table('submission_versions') as batch:
        batch.drop_column('page_count')
        batch.drop_column('page_number')
    with op.batch_alter_table('assignments') as batch:
        batch.drop_index(op.f('ix_assignments_subject_id'))
        batch.drop_constraint('fk_assignments_subject_id_subjects', type_='foreignkey')
        batch.drop_column('subject_id')
    op.drop_index(op.f('ix_student_subject_academic_records_updated_by_user_id'), table_name='student_subject_academic_records')
    op.drop_index(op.f('ix_student_subject_academic_records_import_batch_id'), table_name='student_subject_academic_records')
    op.drop_index(op.f('ix_student_subject_academic_records_subject_id'), table_name='student_subject_academic_records')
    op.drop_index(op.f('ix_student_subject_academic_records_student_id'), table_name='student_subject_academic_records')
    op.drop_table('student_subject_academic_records')