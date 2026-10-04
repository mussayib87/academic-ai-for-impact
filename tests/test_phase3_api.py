import hashlib
from datetime import datetime

import pytest

from ai.risk.predict import DEFAULT_ARTIFACT
from backend.app.models import AuditLog, AcademicRiskOutcome, ModelRegistryEntry, Student, StudentSubjectAcademicRecord, Subject, User


def auth(token):
    return {'Authorization': f'Bearer {token}'}


def test_phase3_readiness_dataset_coverage_and_teacher_only_access(client, teacher_token, student_token):
    teacher = auth(teacher_token)
    student = auth(student_token)

    readiness = client.get('/api/v1/ml/phase3/readiness', headers=teacher)
    assert readiness.status_code == 200
    body = readiness.json()
    assert body['readiness']['training_ready'] is False
    assert body['counts']['independent_outcomes'] == 0
    assert body['counts']['academic_records'] == 0
    assert body['aggregation_strategy'] is None
    assert body['dataset_fingerprint']
    assert body['readiness']['blockers']

    coverage = client.get('/api/v1/ml/phase3/coverage', headers=teacher)
    assert coverage.status_code == 200
    assert coverage.json()['coverage']['by_academic_period'] == {}

    dataset = client.get('/api/v1/ml/phase3/dataset', headers=teacher)
    assert dataset.status_code == 200
    assert dataset.headers['content-type'].startswith('text/csv')
    assert dataset.headers['x-dataset-version'] == 'student-subject-period-v1'
    assert dataset.headers['x-training-eligible'] == 'false'
    assert 'dataset_id,dataset_version,dataset_fingerprint,student_identifier,department,section,academic_period,subject_code' in dataset.text.splitlines()[0]
    assert 'independent_outcome_id,outcome_source,outcome_batch_id,outcome_filename,outcome_checksum' in dataset.text.splitlines()[0]
    assert len(dataset.text.splitlines()) == 1

    for path in (
        '/api/v1/ml/phase3/readiness',
        '/api/v1/ml/phase3/coverage',
        '/api/v1/ml/phase3/dataset',
        '/api/v1/ml/phase3/candidate',
        '/api/v1/ml/phase3/evaluation',
        '/api/v1/ml/phase3/compare',
    ):
        assert client.get(path, headers=student).status_code == 403


def test_phase3_training_and_promotion_are_blocked_without_real_readiness(client, teacher_token):
    teacher = auth(teacher_token)
    artifact_hash = hashlib.sha256(DEFAULT_ARTIFACT.read_bytes()).hexdigest()

    training = client.post(
        '/api/v1/ml/phase3/train',
        json={'aggregation_strategy': 'equal_subject_mean', 'feature_contract': ['fa1_mean', 'fa2_mean']},
        headers=teacher,
    )
    assert training.status_code == 409
    assert '0 independent outcomes available.' in training.json()['detail']['blockers']
    assert hashlib.sha256(DEFAULT_ARTIFACT.read_bytes()).hexdigest() == artifact_hash

    with client.app.state.test_session_factory() as db:
        candidate = ModelRegistryEntry(
            model_id='candidate-manual-test',
            model_version='candidate-manual-test',
            model_type='classification',
            feature_schema=['fa1'],
            status='candidate',
            deployment_status='SHADOW',
        )
        db.add(candidate)
        db.commit()
        candidate_id = candidate.id

    validation = client.post(f'/api/v1/models/registry/{candidate_id}/validate', headers=teacher)
    assert validation.status_code == 409
    assert validation.json()['detail']['result'] == 'blocked'
    promotion = client.post(
        f'/api/v1/models/registry/{candidate_id}/promote',
        json={'explicit_approval': True, 'approval_note': 'test-only blocked candidate'},
        headers=teacher,
    )
    assert promotion.status_code == 409
    assert promotion.json()['detail']['result'] == 'blocked'
    rollback = client.post(f'/api/v1/models/registry/{candidate_id}/rollback', json={'explicit_approval': True, 'rollback_note': 'Fixture rollback request without a previous deployment.'}, headers=teacher)
    assert rollback.status_code == 409
    assert rollback.json()['detail']['result'] == 'blocked'
    assert hashlib.sha256(DEFAULT_ARTIFACT.read_bytes()).hexdigest() == artifact_hash

    with client.app.state.test_session_factory() as db:
        actions = {row.action for row in db.query(AuditLog).all()}
    assert 'phase3.training.blocked' in actions
    assert 'model.candidate.validation.blocked' in actions
    assert 'model.promotion.blocked' in actions
    assert 'model.rollback.blocked' in actions


def test_phase3_candidate_artifacts_are_pipeline_owned_and_teacher_only(client, teacher_token, student_token):
    teacher = auth(teacher_token)
    student = auth(student_token)
    rejected_claim = client.post('/api/v1/models/registry', json={
        'model_version': 'unverified-client-metrics',
        'validation_metrics': {'accuracy': 1.0},
    }, headers=teacher)
    assert rejected_claim.status_code == 422

    metadata_only = client.post('/api/v1/models/registry', json={'model_version': 'metadata-only-entry'}, headers=teacher)
    assert metadata_only.status_code == 201
    assert client.get('/api/v1/ml/phase3/candidate', headers=teacher).json()['status'] == 'unavailable'
    assert client.post('/api/v1/ml/phase3/train', json={'aggregation_strategy': 'equal_subject_mean', 'feature_contract': ['fa1_mean']}, headers=student).status_code == 403
    assert client.post('/api/v1/models/registry/1/validate', headers=student).status_code == 403
    assert client.post('/api/v1/models/registry/1/promote', json={'explicit_approval': True, 'approval_note': 'not authorized'}, headers=student).status_code == 403
    assert client.post('/api/v1/models/registry/1/rollback', json={'explicit_approval': True, 'rollback_note': 'Unauthorized fixture rollback request.'}, headers=student).status_code == 403


def test_phase3_has_no_candidate_evaluation_comparison_or_shap_by_default(client, teacher_token):
    teacher = auth(teacher_token)
    candidate = client.get('/api/v1/ml/phase3/candidate', headers=teacher)
    assert candidate.status_code == 200
    assert candidate.json()['status'] == 'unavailable'
    assert candidate.json()['candidate'] is None

    evaluation = client.get('/api/v1/ml/phase3/evaluation', headers=teacher)
    assert evaluation.status_code == 200
    assert evaluation.json()['status'] == 'unavailable'

    comparison = client.get('/api/v1/ml/phase3/compare', headers=teacher)
    assert comparison.status_code == 200
    assert comparison.json()['status'] == 'unavailable'
    assert comparison.json()['candidate'] is None
    assert comparison.json()['production']['demo_data'] is True
    assert comparison.json()['comparison']['compatible'] is False
    assert comparison.json()['comparison']['feature_contract']['compatible'] is False
    assert comparison.json()['comparison']['dataset_identity']['compatible'] is False
    assert comparison.json()['comparison']['winner'] is None
    assert comparison.json()['comparison']['common_test_set'] is None
    assert any('No candidate model' in blocker for blocker in comparison.json()['comparison']['blockers'])
    assert 'not evidence validating imported academic outcomes' in comparison.json()['production']['metric_context']

    shap = client.get('/api/v1/ml/phase3/shap', headers=teacher)
    assert shap.status_code == 404
    assert 'no validated candidate model exists' in shap.json()['detail'].lower()


def test_sufficient_isolated_fixture_data_trains_candidate_registers_validates_and_explains(client, teacher_token, tmp_path, monkeypatch):
    monkeypatch.setattr('backend.app.main.CANDIDATE_ARTIFACT_DIRECTORY', tmp_path / 'candidate-artifacts')
    monkeypatch.setattr('ai.risk.phase3.APPROVED_AGGREGATION_STRATEGY', 'equal_subject_mean')
    monkeypatch.setattr('ai.risk.phase3.APPROVED_CANDIDATE_FEATURE_CONTRACT', ('fa1_mean', 'fa2_mean'))
    production_hash = hashlib.sha256(DEFAULT_ARTIFACT.read_bytes()).hexdigest()
    with client.app.state.test_session_factory() as db:
        teacher = db.query(User).filter_by(email='teacher@example.com').one()
        subject = Subject(code='EVS', name='Environmental Studies')
        db.add(subject)
        db.flush()
        students = [Student(student_id=f'FIX-{index:03d}', full_name=f'Fixture {index}') for index in range(60)]
        db.add_all(students)
        db.flush()
        labels = ['HIGH'] * 20 + ['MEDIUM'] * 20 + ['LOW'] * 20
        periods = [
            ('2024-S1', datetime(2024, 3, 1), datetime(2024, 4, 1)),
            ('2024-S2', datetime(2024, 9, 1), datetime(2024, 10, 1)),
            ('2025-S1', datetime(2025, 3, 1), datetime(2025, 4, 1)),
        ]
        for period_index, (period, observation_at, outcome_at) in enumerate(periods):
            for student_index, student in enumerate(students):
                label = labels[student_index]
                class_index = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}[label]
                variation = student_index % 4 + period_index
                db.add(StudentSubjectAcademicRecord(
                    student_id=student.id,
                    subject_id=subject.id,
                    academic_period=period,
                    fa1=2 + class_index * 9 + variation,
                    fa1_observed_at=observation_at,
                    fa2=3 + class_index * 8 + variation,
                    fa2_observed_at=observation_at,
                    assignment_mark=5 + class_index * 5,
                    assignment_observed_at=observation_at,
                    attendance_rate=55 + class_index * 15,
                    attendance_observed_at=observation_at,
                    updated_by_user_id=teacher.id,
                ))
                db.add(AcademicRiskOutcome(
                    student_id=student.id,
                    academic_period=period,
                    risk_level=label,
                    observed_at=outcome_at,
                    outcome_source='independent fixture-only label',
                    recorded_by_user_id=teacher.id,
                ))
        db.commit()
        sample_student_id = students[0].id

    headers = auth(teacher_token)
    aggregate_export = client.get(
        '/api/v1/ml/phase3/dataset?aggregation_strategy=equal_subject_mean&feature_contract=fa1_mean&feature_contract=fa2_mean',
        headers=headers,
    )
    assert aggregate_export.status_code == 200
    assert aggregate_export.headers['x-training-eligible'] == 'true'
    assert 'fa1_mean,fa2_mean' in aggregate_export.text.splitlines()[0]
    assert 'source_record_ids,source_subjects,source_record_count' in aggregate_export.text.splitlines()[0]
    assert len(aggregate_export.text.splitlines()) == 181

    training = client.post('/api/v1/ml/phase3/train', json={
        'aggregation_strategy': 'equal_subject_mean',
        'feature_contract': ['fa1_mean', 'fa2_mean'],
    }, headers=headers)
    assert training.status_code == 201, training.text
    body = training.json()
    candidate_version = body['registry_entry']['model_version']
    candidate_id = body['registry_entry']['id']
    assert body['registry_entry']['status'] == 'candidate'
    assert body['registry_entry']['aggregation_strategy'] == 'equal_subject_mean'
    assert body['registry_entry']['test_periods'] == ['2025-S1']
    assert body['production_artifact_changed'] is False
    assert body['evaluation']['test']['sample_count'] == 60
    assert body['evaluation']['test']['class_distribution'] == {'HIGH': 20, 'LOW': 20, 'MEDIUM': 20}
    assert body['evaluation']['feature_importance']['split'] == 'validation'
    assert body['evaluation']['subgroup_evaluation']['evaluated']['subject_or_aggregation']['equal_subject_mean']['sample_count'] == 60
    assert hashlib.sha256(DEFAULT_ARTIFACT.read_bytes()).hexdigest() == production_hash

    listed = client.get('/api/v1/ml/phase3/candidate', headers=headers).json()
    assert listed['status'] == 'available'
    assert listed['candidate']['model_version'] == candidate_version
    assert client.get('/api/v1/ml/phase3/evaluation', headers=headers).json()['status'] == 'available'
    assert client.get('/api/v1/ml/phase3/compare', headers=headers).json()['candidate']['model_version'] == candidate_version

    validation = client.post(f'/api/v1/models/registry/{candidate_id}/validate', headers=headers)
    assert validation.status_code == 200, validation.text
    approval = client.post(f'/api/v1/models/registry/{candidate_id}/approve', json={
        'explicit_approval': True,
        'approval_note': 'Fixture-only approval for pipeline behavior verification.',
    }, headers=headers)
    assert approval.status_code == 200, approval.text
    assert approval.json()['production_changed'] is False
    shap = client.get(f'/api/v1/ml/phase3/shap?student_id={sample_student_id}', headers=headers)
    assert shap.status_code == 200, shap.text
    explanation = shap.json()
    assert explanation['model_version'] == candidate_version
    assert explanation['base_value'] + sum(explanation['contributions'].values()) == pytest.approx(explanation['probability'], abs=1e-4)
    promotion = client.post(f'/api/v1/models/registry/{candidate_id}/promote', json={
        'explicit_approval': True,
        'approval_note': 'Fixture-only API test; production promotion is never requested.',
    }, headers=headers)
    assert promotion.status_code == 409
    assert promotion.json()['detail']['result'] == 'blocked'
    assert hashlib.sha256(DEFAULT_ARTIFACT.read_bytes()).hexdigest() == production_hash
