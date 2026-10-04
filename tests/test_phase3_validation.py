from datetime import datetime

import pytest

from ai.risk.candidate import explain_candidate, train_candidate
from ai.risk.predict import DEFAULT_ARTIFACT
from ai.risk.phase3 import build_phase3_dataset, temporal_split
from backend.app.models import (
    AcademicDataImportBatch,
    AcademicDataImportRow,
    AcademicRiskOutcome,
    Student,
    StudentSubjectAcademicRecord,
    StudentSubjectAcademicRecordHistory,
    Subject,
    User,
)
import hashlib


def _add_subject_observation(db, student_id, subject_id, *, period='2026-S1', observed_at=datetime(2026, 9, 1), fa2_at=None):
    teacher = db.query(User).filter_by(email='teacher@example.com').one()
    record = StudentSubjectAcademicRecord(
        student_id=student_id,
        subject_id=subject_id,
        academic_period=period,
        fa1=20,
        fa1_observed_at=observed_at,
        fa2=18,
        fa2_observed_at=fa2_at or observed_at,
        assignment_mark=21,
        assignment_observed_at=observed_at,
        attendance_rate=90,
        attendance_observed_at=observed_at,
        updated_by_user_id=teacher.id,
    )
    db.add(record)
    db.flush()
    outcome = AcademicRiskOutcome(
        student_id=student_id,
        academic_period=period,
        risk_level='MEDIUM',
        observed_at=datetime(2026, 9, 15),
        outcome_source='independent faculty review',
        recorded_by_user_id=teacher.id,
    )
    db.add(outcome)
    db.commit()
    return record


def test_readiness_with_zero_outcomes_is_false_and_names_measured_blockers(client):
    with client.app.state.test_session_factory() as db:
        result = build_phase3_dataset(db)
    assert result['readiness']['training_ready'] is False
    assert result['readiness']['evidence']['independent_outcomes'] == 0
    assert any('0 independent outcomes' in item for item in result['readiness']['blockers'])
    assert any('aggregation strategy' in item.lower() for item in result['readiness']['blockers'])


def test_valid_period_matched_observation_is_temporally_aligned_but_not_trainable_without_aggregation(client):
    with client.app.state.test_session_factory() as db:
        student = db.query(Student).filter_by(student_id='T-001').one()
        subject = Subject(code='CN', name='Computer Networks')
        db.add(subject)
        db.flush()
        _add_subject_observation(db, student.id, subject.id)
        result = build_phase3_dataset(db)
    row = result['rows'][0]
    assert row['student_identifier'] == 'T-001'
    assert row['subject_code'] == 'CN'
    assert row['academic_period'] == '2026-S1'
    assert row['risk_target'] == 'MEDIUM'
    assert row['temporally_aligned'] is True
    assert row['candidate_eligible'] is False
    assert result['counts']['temporally_aligned_observations'] == 1
    assert result['readiness']['training_ready'] is False
    coverage = result['coverage']['by_period_and_subject']['2026-S1/CN']
    assert coverage['observation_date_coverage_percent'] == 100


def test_future_feature_is_excluded_and_cannot_label_earlier_outcome(client):
    with client.app.state.test_session_factory() as db:
        student = db.query(Student).filter_by(student_id='T-001').one()
        subject = Subject(code='CN', name='Computer Networks')
        db.add(subject)
        db.flush()
        _add_subject_observation(db, student.id, subject.id, fa2_at=datetime(2026, 10, 1))
        result = build_phase3_dataset(db)
    row = result['rows'][0]
    assert row['temporally_aligned'] is False
    assert row['fa2'] is None
    assert row['risk_target'] is None
    assert 'fa2_observed_after_outcome' in row['exclusion_reasons']
    assert result['counts']['temporally_invalid_observations'] == 1


def test_import_or_update_timestamps_do_not_make_missing_source_dates_temporally_valid(client):
    with client.app.state.test_session_factory() as db:
        student = db.query(Student).filter_by(student_id='T-001').one()
        subject = Subject(code='CN', name='Computer Networks')
        db.add(subject)
        db.flush()
        teacher = db.query(User).filter_by(email='teacher@example.com').one()
        batch = AcademicDataImportBatch(
            dataset_type='subject_records',
            source_filename='marks.csv',
            file_checksum='a' * 64,
            imported_by_user_id=teacher.id,
        )
        db.add(batch)
        db.flush()
        record = StudentSubjectAcademicRecord(
            student_id=student.id,
            subject_id=subject.id,
            academic_period='2026-S1',
            fa1=20,
            fa2=18,
            assignment_mark=21,
            attendance_rate=90,
            import_batch_id=batch.id,
            updated_by_user_id=teacher.id,
        )
        db.add(record)
        db.add(AcademicRiskOutcome(
            student_id=student.id,
            academic_period='2026-S1',
            risk_level='MEDIUM',
            observed_at=datetime(2026, 9, 15),
            outcome_source='independent faculty review',
        ))
        db.commit()
        result = build_phase3_dataset(db)
    row = result['rows'][0]
    assert row['temporally_aligned'] is False
    assert row['risk_target'] is None
    assert 'missing_source_observation_date' in row['exclusion_reasons']


@pytest.mark.parametrize('source', [
    'model prediction from faculty dashboard',
    'SHAP analysis',
    'inference output',
    'synthetic prediction',
    'model-prediction export',
    'synthetic label',
    'AI-generated label',
])
def test_model_derived_outcomes_are_not_candidate_targets(client, source):
    with client.app.state.test_session_factory() as db:
        student = db.query(Student).filter_by(student_id='T-001').one()
        subject = Subject(code='CN', name='Computer Networks')
        db.add(subject)
        db.flush()
        _add_subject_observation(db, student.id, subject.id)
        outcome = db.query(AcademicRiskOutcome).filter_by(student_id=student.id, academic_period='2026-S1').one()
        outcome.outcome_source = source
        db.commit()
        result = build_phase3_dataset(db)
    row = result['rows'][0]
    assert row['risk_target'] is None
    assert row['candidate_eligible'] is False
    assert 'invalid_or_model_derived_outcome' in row['exclusion_reasons']


def test_dataset_fingerprint_is_stable_and_changes_when_source_data_changes(client):
    with client.app.state.test_session_factory() as db:
        student = db.query(Student).filter_by(student_id='T-001').one()
        subject = Subject(code='CN', name='Computer Networks')
        db.add(subject)
        db.flush()
        record = _add_subject_observation(db, student.id, subject.id)
        first = build_phase3_dataset(db)
        same = build_phase3_dataset(db)
        assert first['dataset_fingerprint'] == same['dataset_fingerprint']
        record.fa1 = 19
        db.commit()
        changed = build_phase3_dataset(db)
        proposed_contract = build_phase3_dataset(
            db,
            aggregation_strategy='equal_subject_mean',
            feature_contract=['fa1_mean'],
        )
    assert changed['dataset_fingerprint'] != first['dataset_fingerprint']
    assert proposed_contract['dataset_fingerprint'] != changed['dataset_fingerprint']


def test_temporal_split_uses_earlier_periods_for_train_validation_and_latest_for_test():
    periods = ['2025-S1', '2025-S2', '2026-S1', '2026-S2']
    split = temporal_split(periods)
    assert split == {
        'training_periods': ['2025-S1', '2025-S2'],
        'validation_periods': ['2026-S1'],
        'test_periods': ['2026-S2'],
    }
    with pytest.raises(ValueError, match='at least 3'):
        temporal_split(['2026-S1', '2026-S2'])


def test_insufficient_periods_and_class_coverage_are_explicit(client):
    with client.app.state.test_session_factory() as db:
        student = db.query(Student).filter_by(student_id='T-001').one()
        subject = Subject(code='CN', name='Computer Networks')
        db.add(subject)
        db.flush()
        _add_subject_observation(db, student.id, subject.id)
        result = build_phase3_dataset(db)
    blockers = result['readiness']['blockers']
    assert any('Only 1 academic period' in item for item in blockers)
    assert any('Insufficient HIGH outcomes' in item for item in blockers)
    assert any('Insufficient LOW outcomes' in item for item in blockers)
    assert result['readiness']['evidence']['students_per_risk_class']['MEDIUM'] == 1


def test_invalid_period_ranges_and_future_outcomes_are_not_eligible(client):
    with client.app.state.test_session_factory() as db:
        student = db.query(Student).filter_by(student_id='T-001').one()
        subject = Subject(code='CN', name='Computer Networks')
        db.add(subject)
        db.flush()
        record = StudentSubjectAcademicRecord(
            student_id=student.id,
            subject_id=subject.id,
            academic_period='2026-S3',
            fa1=27,
            fa1_observed_at=datetime(2026, 9, 1),
            fa2=18,
            fa2_observed_at=datetime(2026, 9, 1),
            assignment_mark=21,
            assignment_observed_at=datetime(2026, 9, 1),
            attendance_rate=90,
            attendance_observed_at=datetime(2026, 9, 1),
        )
        db.add(record)
        db.add(AcademicRiskOutcome(
            student_id=student.id,
            academic_period='2026-S3',
            risk_level='NOT_A_CLASS',
            observed_at=datetime(2027, 1, 1),
            outcome_source='independent source',
        ))
        db.commit()
        result = build_phase3_dataset(db)
    assert result['counts']['invalid_academic_periods'] == 1
    assert result['counts']['invalid_mark_records'] == 1
    assert result['counts']['invalid_outcomes'] == 1
    assert result['counts']['future_observations'] == 1
    assert result['rows'][0]['risk_target'] is None
    assert 'fa1_outside_valid_range' in result['rows'][0]['exclusion_reasons']
    assert 'invalid_academic_period' in result['rows'][0]['exclusion_reasons']


def test_rejected_conflicting_import_row_retains_source_row_identity_and_reason(client):
    with client.app.state.test_session_factory() as db:
        teacher = db.query(User).filter_by(email='teacher@example.com').one()
        batch = AcademicDataImportBatch(
            dataset_type='subject_records',
            source_filename='conflicting-marks.csv',
            file_checksum='b' * 64,
            imported_by_user_id=teacher.id,
            validation_errors=[{
                'row': 8,
                'student_id': 'UNKNOWN-8',
                'subject_code': 'CN',
                'academic_period': '2026-S3',
                'errors': ['Conflicting duplicate fa1 values.'],
            }],
        )
        db.add(batch)
        db.flush()
        db.add(AcademicDataImportRow(
            batch_id=batch.id,
            dataset_type='subject_records',
            row_checksum='c' * 64,
            row_number=8,
            status='rejected',
            errors=['Conflicting duplicate fa1 values.'],
        ))
        db.commit()
        result = build_phase3_dataset(db)
    rejected = result['rejected_rows'][0]
    assert rejected == {
        'row_number': 8,
        'usn': 'UNKNOWN-8',
        'subject_code': 'CN',
        'academic_period': '2026-S3',
        'reason': ['Conflicting duplicate fa1 values.'],
        'source_filename': 'conflicting-marks.csv',
        'source_batch_id': 1,
    }
    assert result['counts']['conflicting_records'] == 1
    assert result['counts']['unknown_students'] == 1


def test_corrected_record_is_not_assumed_to_have_existed_as_of_outcome(client):
    with client.app.state.test_session_factory() as db:
        student = db.query(Student).filter_by(student_id='T-001').one()
        subject = Subject(code='CN', name='Computer Networks')
        db.add(subject)
        db.flush()
        record = _add_subject_observation(db, student.id, subject.id)
        db.add(StudentSubjectAcademicRecordHistory(
            academic_record_id=record.id,
            change_kind='manual',
            fa1=20,
            fa1_observed_at=datetime(2026, 9, 1),
            fa2=18,
            fa2_observed_at=datetime(2026, 9, 1),
            assignment_mark=21,
            assignment_observed_at=datetime(2026, 9, 1),
            attendance_rate=90,
            attendance_observed_at=datetime(2026, 9, 1),
        ))
        db.add(StudentSubjectAcademicRecordHistory(
            academic_record_id=record.id,
            change_kind='manual',
            fa1=21,
            fa1_observed_at=datetime(2026, 9, 2),
            fa2=18,
            fa2_observed_at=datetime(2026, 9, 1),
            assignment_mark=21,
            assignment_observed_at=datetime(2026, 9, 1),
            attendance_rate=90,
            attendance_observed_at=datetime(2026, 9, 1),
        ))
        db.commit()
        result = build_phase3_dataset(db)
    assert result['counts']['revised_records'] == 1
    assert result['rows'][0]['temporally_aligned'] is False
    assert result['rows'][0]['risk_target'] is None
    assert 'revised_record_as_of_value_unverified' in result['rows'][0]['exclusion_reasons']


def test_database_update_timestamp_does_not_change_dataset_fingerprint(client):
    with client.app.state.test_session_factory() as db:
        student = db.query(Student).filter_by(student_id='T-001').one()
        subject = Subject(code='CN', name='Computer Networks')
        db.add(subject)
        db.flush()
        record = _add_subject_observation(db, student.id, subject.id)
        first = build_phase3_dataset(db)
        record.updated_at = datetime(2026, 10, 2, 23, 59)
        db.commit()
        later_updated = build_phase3_dataset(db)
    assert later_updated['dataset_fingerprint'] == first['dataset_fingerprint']


def test_candidate_training_uses_temporal_holdouts_and_writes_only_candidate_artifacts(tmp_path):
    import pandas as pd

    rows = []
    periods = ['2024-S1', '2024-S2', '2025-S1']
    for period_index, period in enumerate(periods):
        for label_index, label in enumerate(('HIGH', 'MEDIUM', 'LOW')):
            for student_index in range(6):
                rows.append({
                    'student_identifier': f'{period}-{label}-{student_index}',
                    'academic_period': period,
                    'subject_or_aggregation': 'fixture student-period records only',
                    'fa1': 2 + 9 * label_index + (student_index % 3),
                    'fa2': 3 + 8 * label_index + ((student_index + period_index) % 3),
                    'risk_target': label,
                })
    frame = pd.DataFrame(rows)
    production_hash = hashlib.sha256(DEFAULT_ARTIFACT.read_bytes()).hexdigest()
    result = train_candidate(
        frame,
        output_directory=tmp_path / 'models' / 'candidates',
        feature_contract=['fa1', 'fa2'],
        target_column='risk_target',
        period_column='academic_period',
        identity_column='student_identifier',
        dataset_id='p3-fixture-dataset',
        dataset_version='fixture-v1',
        dataset_fingerprint='f' * 64,
        target_definition='Independent fixture-only target',
        aggregation_strategy='fixture student-period records only',
        random_seed=37,
    )
    metadata = result['metadata']
    assert result['artifact_path'].parent == tmp_path / 'models' / 'candidates'
    assert result['artifact_path'].exists()
    assert metadata['training_periods'] == ['2024-S1']
    assert metadata['validation_periods'] == ['2024-S2']
    assert metadata['test_periods'] == ['2025-S1']
    assert metadata['feature_contract'] == ['fa1', 'fa2']
    assert metadata['dataset_fingerprint'] == 'f' * 64
    assert metadata['test_metrics']['sample_count'] == 18
    assert metadata['test_metrics']['class_distribution'] == {'HIGH': 6, 'LOW': 6, 'MEDIUM': 6}
    assert metadata['test_metrics']['accuracy'] >= 0.9
    assert metadata['test_metrics']['macro_f1'] >= 0.9
    assert metadata['feature_importance']['split'] == 'validation'
    assert metadata['feature_importance']['sample_count'] == 18
    assert metadata['subgroup_evaluation']['split'] == 'test'
    assert metadata['subgroup_evaluation']['withheld_for_insufficient_sample']['subject_or_aggregation']['fixture student-period records only'] == 18
    assert metadata['model_version'].startswith('candidate-')
    assert hashlib.sha256(DEFAULT_ARTIFACT.read_bytes()).hexdigest() == production_hash

    explanation = explain_candidate(result['artifact_path'], {'fa1': 4.0, 'fa2': 5.0}, target_class='HIGH')
    assert explanation['model_version'] == metadata['model_version']
    assert explanation['target_class'] == 'HIGH'
    assert explanation['base_value'] + sum(explanation['contributions'].values()) == pytest.approx(explanation['probability'], abs=1e-4)
    assert set(explanation['contributions']) == {'fa1', 'fa2'}


def test_candidate_trainer_rejects_implicit_contract_and_duplicate_student_period_rows(tmp_path):
    import pandas as pd

    frame = pd.DataFrame([
        {'student_identifier': 'S-1', 'academic_period': '2024-S1', 'fa1': 10, 'risk_target': 'HIGH'},
        {'student_identifier': 'S-1', 'academic_period': '2024-S1', 'fa1': 11, 'risk_target': 'HIGH'},
    ])
    with pytest.raises(ValueError, match='feature contract'):
        train_candidate(
            frame,
            output_directory=tmp_path,
            feature_contract=[],
            target_column='risk_target',
            period_column='academic_period',
            identity_column='student_identifier',
            dataset_id='duplicate-fixture',
            dataset_version='fixture-v1',
            dataset_fingerprint='a' * 64,
            target_definition='fixture target',
            aggregation_strategy='explicit test fixture aggregation',
        )
