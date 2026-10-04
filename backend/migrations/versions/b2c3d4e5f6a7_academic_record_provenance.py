"""add provenance to imported academic records

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-30 00:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table_name in ('attendance', 'assessments', 'marks', 'learning_activities'):
        inspector = sa.inspect(op.get_bind())
        columns = {column['name'] for column in inspector.get_columns(table_name)}
        indexes = {index['name'] for index in inspector.get_indexes(table_name)}
        foreign_keys = {key['name'] for key in inspector.get_foreign_keys(table_name)}
        index_name = op.f(f'ix_{table_name}_import_batch_id')
        foreign_key_name = f'fk_{table_name}_import_batch'
        if 'import_batch_id' in columns and index_name in indexes and foreign_key_name in foreign_keys:
            continue
        with op.batch_alter_table(table_name) as batch:
            if 'import_batch_id' not in columns:
                batch.add_column(sa.Column('import_batch_id', sa.Integer(), nullable=True))
            if foreign_key_name not in foreign_keys:
                batch.create_foreign_key(foreign_key_name, 'academic_data_import_batches', ['import_batch_id'], ['id'], ondelete='SET NULL')
            if index_name not in indexes:
                batch.create_index(index_name, ['import_batch_id'], unique=False)


def downgrade() -> None:
    for table_name in ('learning_activities', 'marks', 'assessments', 'attendance'):
        with op.batch_alter_table(table_name) as batch:
            batch.drop_index(op.f(f'ix_{table_name}_import_batch_id'))
            batch.drop_constraint(f'fk_{table_name}_import_batch', type_='foreignkey')
            batch.drop_column('import_batch_id')