"""add verifiable model registry metadata

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'model_registry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('model_id', sa.String(length=80), nullable=False),
        sa.Column('model_version', sa.String(length=80), nullable=False),
        sa.Column('model_type', sa.String(length=40), nullable=False),
        sa.Column('feature_schema', sa.JSON(), nullable=True),
        sa.Column('feature_contract_version', sa.String(length=80), nullable=True),
        sa.Column('training_period', sa.String(length=40), nullable=True),
        sa.Column('training_dataset_version', sa.String(length=160), nullable=True),
        sa.Column('training_dataset_hash', sa.String(length=128), nullable=True),
        sa.Column('training_timestamp', sa.DateTime(), nullable=True),
        sa.Column('validation_metrics', sa.JSON(), nullable=True),
        sa.Column('artifact_identifier', sa.String(length=512), nullable=True),
        sa.Column('artifact_hash', sa.String(length=128), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('metrics', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('deployment_status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('model_id'),
        sa.UniqueConstraint('model_version'),
    )
    op.create_index(op.f('ix_model_registry_model_id'), 'model_registry', ['model_id'], unique=True)
    op.create_index(op.f('ix_model_registry_model_version'), 'model_registry', ['model_version'], unique=True)
    op.create_index(op.f('ix_model_registry_model_type'), 'model_registry', ['model_type'], unique=False)
    op.create_index(op.f('ix_model_registry_status'), 'model_registry', ['status'], unique=False)
    op.create_index(op.f('ix_model_registry_deployment_status'), 'model_registry', ['deployment_status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_model_registry_deployment_status'), table_name='model_registry')
    op.drop_index(op.f('ix_model_registry_status'), table_name='model_registry')
    op.drop_index(op.f('ix_model_registry_model_type'), table_name='model_registry')
    op.drop_index(op.f('ix_model_registry_model_version'), table_name='model_registry')
    op.drop_index(op.f('ix_model_registry_model_id'), table_name='model_registry')
    op.drop_table('model_registry')
