"""add local model deployment selector and immutable event history

Revision ID: a7b8c9d0e1f2
Revises: bb2233445566
Create Date: 2026-10-03 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'bb2233445566'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('model_registry') as batch:
        batch.add_column(sa.Column('rejected_by_user_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('rejected_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('rejection_reason', sa.Text(), nullable=True))
        batch.create_foreign_key('fk_model_registry_rejected_by_user_id_users', 'users', ['rejected_by_user_id'], ['id'], ondelete='SET NULL')
        batch.create_index('ix_model_registry_rejected_by_user_id', ['rejected_by_user_id'], unique=False)

    op.create_table(
        'model_deployment_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('active_model_version', sa.String(length=80), nullable=False),
        sa.Column('active_artifact_hash', sa.String(length=128), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'model_deployment_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event', sa.String(length=30), nullable=False),
        sa.Column('previous_version', sa.String(length=80), nullable=True),
        sa.Column('new_version', sa.String(length=80), nullable=True),
        sa.Column('candidate_version', sa.String(length=80), nullable=True),
        sa.Column('artifact_hash', sa.String(length=128), nullable=True),
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('actor_role', sa.String(length=20), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('rollback_of_event_id', sa.Integer(), nullable=True),
        sa.Column('dataset_hash', sa.String(length=128), nullable=True),
        sa.Column('feature_contract', sa.JSON(), nullable=True),
        sa.Column('evaluation_reference', sa.JSON(), nullable=True),
        sa.Column('previous_state', sa.JSON(), nullable=True),
        sa.Column('new_state', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['rollback_of_event_id'], ['model_deployment_events.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_model_deployment_events_event', 'model_deployment_events', ['event'], unique=False)
    op.create_index('ix_model_deployment_events_actor_user_id', 'model_deployment_events', ['actor_user_id'], unique=False)
    op.create_index('ix_model_deployment_events_occurred_at', 'model_deployment_events', ['occurred_at'], unique=False)
    op.create_index('ix_model_deployment_events_status', 'model_deployment_events', ['status'], unique=False)
    op.create_index('ix_model_deployment_events_candidate_version', 'model_deployment_events', ['candidate_version'], unique=False)
    if op.get_bind().dialect.name == 'sqlite':
        op.execute("""
            CREATE TRIGGER trg_model_deployment_events_no_update
            BEFORE UPDATE ON model_deployment_events
            BEGIN
                SELECT RAISE(ABORT, 'model deployment events are immutable');
            END
        """)
        op.execute("""
            CREATE TRIGGER trg_model_deployment_events_no_delete
            BEFORE DELETE ON model_deployment_events
            BEGIN
                SELECT RAISE(ABORT, 'model deployment events are immutable');
            END
        """)


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        op.execute('DROP TRIGGER IF EXISTS trg_model_deployment_events_no_delete')
        op.execute('DROP TRIGGER IF EXISTS trg_model_deployment_events_no_update')
    op.drop_index('ix_model_deployment_events_candidate_version', table_name='model_deployment_events')
    op.drop_index('ix_model_deployment_events_status', table_name='model_deployment_events')
    op.drop_index('ix_model_deployment_events_occurred_at', table_name='model_deployment_events')
    op.drop_index('ix_model_deployment_events_actor_user_id', table_name='model_deployment_events')
    op.drop_index('ix_model_deployment_events_event', table_name='model_deployment_events')
    op.drop_table('model_deployment_events')
    op.drop_table('model_deployment_state')
    with op.batch_alter_table('model_registry') as batch:
        batch.drop_index('ix_model_registry_rejected_by_user_id')
        batch.drop_constraint('fk_model_registry_rejected_by_user_id_users', type_='foreignkey')
        batch.drop_column('rejection_reason')
        batch.drop_column('rejected_at')
        batch.drop_column('rejected_by_user_id')
