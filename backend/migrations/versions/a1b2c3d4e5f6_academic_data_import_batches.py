"""track academic data import batches and rows

Revision ID: a1b2c3d4e5f6
Revises: 7367c2204554
Create Date: 2026-09-30 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '7367c2204554'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'academic_data_import_batches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dataset_type', sa.String(length=40), nullable=False),
        sa.Column('source_filename', sa.String(length=255), nullable=False),
        sa.Column('file_checksum', sa.String(length=64), nullable=False),
        sa.Column('imported_by_user_id', sa.Integer(), nullable=False),
        sa.Column('imported_rows', sa.Integer(), nullable=False),
        sa.Column('rejected_rows', sa.Integer(), nullable=False),
        sa.Column('duplicate_rows', sa.Integer(), nullable=False),
        sa.Column('validation_errors', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['imported_by_user_id'], ['users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('dataset_type', 'file_checksum', name='uq_academic_import_type_checksum'),
    )
    op.create_index(op.f('ix_academic_data_import_batches_dataset_type'), 'academic_data_import_batches', ['dataset_type'], unique=False)
    op.create_index(op.f('ix_academic_data_import_batches_imported_by_user_id'), 'academic_data_import_batches', ['imported_by_user_id'], unique=False)
    op.create_table(
        'academic_data_import_rows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('dataset_type', sa.String(length=40), nullable=False),
        sa.Column('row_checksum', sa.String(length=64), nullable=False),
        sa.Column('row_number', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=True),
        sa.Column('errors', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['batch_id'], ['academic_data_import_batches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('dataset_type', 'row_checksum', name='uq_academic_import_type_row'),
    )
    op.create_index(op.f('ix_academic_data_import_rows_batch_id'), 'academic_data_import_rows', ['batch_id'], unique=False)
    op.create_index(op.f('ix_academic_data_import_rows_dataset_type'), 'academic_data_import_rows', ['dataset_type'], unique=False)
    op.create_index(op.f('ix_academic_data_import_rows_student_id'), 'academic_data_import_rows', ['student_id'], unique=False)
    with op.batch_alter_table('academic_momentum') as batch:
        batch.add_column(sa.Column('import_batch_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_momentum_import_batch', 'academic_data_import_batches', ['import_batch_id'], ['id'], ondelete='SET NULL')
        batch.create_index(op.f('ix_academic_momentum_import_batch_id'), ['import_batch_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('academic_momentum') as batch:
        batch.drop_index(op.f('ix_academic_momentum_import_batch_id'))
        batch.drop_constraint('fk_momentum_import_batch', type_='foreignkey')
        batch.drop_column('import_batch_id')
    op.drop_index(op.f('ix_academic_data_import_rows_student_id'), table_name='academic_data_import_rows')
    op.drop_index(op.f('ix_academic_data_import_rows_dataset_type'), table_name='academic_data_import_rows')
    op.drop_index(op.f('ix_academic_data_import_rows_batch_id'), table_name='academic_data_import_rows')
    op.drop_table('academic_data_import_rows')
    op.drop_index(op.f('ix_academic_data_import_batches_imported_by_user_id'), table_name='academic_data_import_batches')
    op.drop_index(op.f('ix_academic_data_import_batches_dataset_type'), table_name='academic_data_import_batches')
    op.drop_table('academic_data_import_batches')