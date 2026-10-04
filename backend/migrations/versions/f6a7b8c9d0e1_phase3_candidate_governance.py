"""add candidate provenance and governance lifecycle fields

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('model_registry') as batch:
        batch.add_column(sa.Column('created_by_user_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('dataset_id', sa.String(length=80), nullable=True))
        batch.add_column(sa.Column('dataset_version', sa.String(length=80), nullable=True))
        batch.add_column(sa.Column('dataset_fingerprint', sa.String(length=64), nullable=True))
        batch.add_column(sa.Column('target_definition', sa.Text(), nullable=True))
        batch.add_column(sa.Column('aggregation_strategy', sa.Text(), nullable=True))
        batch.add_column(sa.Column('training_periods', sa.JSON(), nullable=True))
        batch.add_column(sa.Column('validation_periods', sa.JSON(), nullable=True))
        batch.add_column(sa.Column('test_periods', sa.JSON(), nullable=True))
        batch.add_column(sa.Column('algorithm', sa.String(length=80), nullable=True))
        batch.add_column(sa.Column('hyperparameters', sa.JSON(), nullable=True))
        batch.add_column(sa.Column('random_seed', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('validation_status', sa.String(length=30), nullable=True))
        batch.add_column(sa.Column('approval_status', sa.String(length=30), nullable=True))
        batch.add_column(sa.Column('approved_by_user_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('approved_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('previous_production_model_version', sa.String(length=80), nullable=True))
        batch.add_column(sa.Column('promoted_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('retired_at', sa.DateTime(), nullable=True))
        batch.create_foreign_key('fk_model_registry_created_by_user_id_users', 'users', ['created_by_user_id'], ['id'], ondelete='SET NULL')
        batch.create_foreign_key('fk_model_registry_approved_by_user_id_users', 'users', ['approved_by_user_id'], ['id'], ondelete='SET NULL')
        batch.create_index('ix_model_registry_created_by_user_id', ['created_by_user_id'], unique=False)
        batch.create_index('ix_model_registry_dataset_id', ['dataset_id'], unique=False)
        batch.create_index('ix_model_registry_dataset_fingerprint', ['dataset_fingerprint'], unique=False)
        batch.create_index('ix_model_registry_approved_by_user_id', ['approved_by_user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('model_registry') as batch:
        batch.drop_index('ix_model_registry_approved_by_user_id')
        batch.drop_index('ix_model_registry_dataset_fingerprint')
        batch.drop_index('ix_model_registry_dataset_id')
        batch.drop_index('ix_model_registry_created_by_user_id')
        batch.drop_constraint('fk_model_registry_approved_by_user_id_users', type_='foreignkey')
        batch.drop_constraint('fk_model_registry_created_by_user_id_users', type_='foreignkey')
        for column in (
            'retired_at', 'promoted_at', 'previous_production_model_version', 'approved_at',
            'approved_by_user_id', 'approval_status', 'validation_status', 'random_seed',
            'hyperparameters', 'algorithm', 'test_periods', 'validation_periods',
            'training_periods', 'aggregation_strategy', 'target_definition',
            'dataset_fingerprint', 'dataset_version', 'dataset_id', 'created_by_user_id',
        ):
            batch.drop_column(column)
