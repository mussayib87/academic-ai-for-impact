from backend.app.database import session
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from types import SimpleNamespace


def test_engine_options_are_dialect_aware(monkeypatch, tmp_path):
    captured = {}

    def fake_create_engine(url, **options):
        captured['url'] = url
        captured['options'] = options
        return object()

    monkeypatch.setattr(session, 'create_engine', fake_create_engine)
    session.create_database_engine('postgresql+psycopg://user:pass@localhost/example')
    assert 'connect_args' not in captured['options']
    assert captured['options']['pool_pre_ping'] is True

    database_path = tmp_path / 'nested' / 'local.db'
    session.create_database_engine(f'sqlite:///{database_path.as_posix()}')
    assert captured['options']['connect_args'] == {'check_same_thread': False}
    assert database_path.parent.is_dir()


def test_academic_import_migration_applies_to_sqlite_without_touching_project_db(monkeypatch, tmp_path):
    database_path = tmp_path / 'migration-check.db'
    database_url = f'sqlite:///{database_path.as_posix()}'
    monkeypatch.setattr('backend.app.config.get_settings', lambda: SimpleNamespace(database_url=database_url))
    configuration = Config('alembic.ini')

    command.upgrade(configuration, 'head')

    inspector = inspect(create_engine(database_url))
    assert {'academic_data_import_batches', 'academic_data_import_rows'} <= set(inspector.get_table_names())
    assert 'student_subject_academic_records' in inspector.get_table_names()
    assert 'student_subject_academic_record_history' in inspector.get_table_names()
    assert 'academic_risk_outcomes' in inspector.get_table_names()
    subject_record_columns = {column['name'] for column in inspector.get_columns('student_subject_academic_records')}
    assert {'academic_period', 'fa1_observed_at', 'fa2_observed_at', 'assignment_observed_at', 'attendance_observed_at'} <= subject_record_columns
    assert 'academic_record_id' in {column['name'] for column in inspector.get_columns('academic_data_import_rows')}
    assert 'subject_id' in {column['name'] for column in inspector.get_columns('assignments')}
    assert {'page_number', 'page_count'} <= {column['name'] for column in inspector.get_columns('submission_versions')}
    assert 'page_count' in {column['name'] for column in inspector.get_columns('submissions')}
    with create_engine(database_url).connect() as connection:
        subjects = set(connection.execute(__import__('sqlalchemy').text('SELECT code FROM subjects')).scalars())
    assert {'EVS', 'CN', 'TOC', 'RM', 'SE'} <= subjects
    assert 'import_batch_id' in {column['name'] for column in inspector.get_columns('academic_momentum')}
    registry_columns = {column['name'] for column in inspector.get_columns('model_registry')}
    assert {'rejected_by_user_id', 'rejected_at', 'rejection_reason'} <= registry_columns
    assert {'model_deployment_state', 'model_deployment_events'} <= set(inspector.get_table_names())
    deployment_event_columns = {column['name'] for column in inspector.get_columns('model_deployment_events')}
    assert {
        'event', 'previous_version', 'new_version', 'artifact_hash', 'actor_user_id',
        'actor_role', 'occurred_at', 'reason', 'status', 'rollback_of_event_id',
        'dataset_hash', 'feature_contract', 'evaluation_reference', 'previous_state', 'new_state',
    } <= deployment_event_columns
    with create_engine(database_url).connect() as connection:
        deployment_triggers = set(connection.execute(__import__('sqlalchemy').text(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'model_deployment_events'"
        )).scalars())
    assert deployment_triggers == {'trg_model_deployment_events_no_update', 'trg_model_deployment_events_no_delete'}
    assert {
        'created_by_user_id', 'dataset_id', 'dataset_version', 'dataset_fingerprint',
        'target_definition', 'aggregation_strategy', 'training_periods',
        'validation_periods', 'test_periods', 'algorithm', 'hyperparameters',
        'random_seed', 'validation_status', 'approval_status', 'approved_by_user_id',
        'approved_at', 'previous_production_model_version', 'promoted_at', 'retired_at',
    } <= registry_columns
    for table_name in ('attendance', 'assessments', 'marks', 'learning_activities'):
        assert 'import_batch_id' in {column['name'] for column in inspector.get_columns(table_name)}