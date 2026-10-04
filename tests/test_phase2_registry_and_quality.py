import hashlib

import pytest

from ai.risk.features import FEATURES
from ai.risk.predict import DEFAULT_ARTIFACT, load_artifact, predict as predict_risk
from backend.app.main import student_features
from backend.app.models import AcademicMomentum, ModelRegistryEntry, RiskPrediction, RiskSnapshot, Student


def test_registry_reports_real_production_artifact_and_unavailable_candidate_metadata(client, teacher_token):
    headers = {'Authorization': f'Bearer {teacher_token}'}
    registry = client.get('/api/v1/models/registry', headers=headers)
    assert registry.status_code == 200
    payload = registry.json()
    production = payload['current_production_model']
    artifact = load_artifact()
    with client.app.state.test_session_factory() as db:
        assert db.query(ModelRegistryEntry).count() == 0
    assert production['model_version'] == artifact['metadata']['model_version']
    assert production['feature_contract'] == FEATURES
    assert production['training_timestamp'] == artifact['metadata']['trained_at']
    assert production['artifact_hash'] == hashlib.sha256(DEFAULT_ARTIFACT.read_bytes()).hexdigest()
    assert production['status'] == 'production'
    assert production['training_provenance']['demo_data'] is True
    assert payload['history'] == []

    created = client.post('/api/v1/models/registry', json={'model_version': 'risk-candidate-no-metrics', 'model_type': 'classification'}, headers=headers)
    assert created.status_code == 201
    candidate = created.json()
    assert candidate['status'] == 'candidate'
    assert candidate['validation_metrics'] is None
    assert candidate['training_timestamp'] is None
    assert candidate['artifact_hash'] is None
    assert candidate['notes'] is None
    validated = client.post(
        '/api/v1/models/registry',
        json={'model_version': 'unverified-validated', 'status': 'validated', 'validation_metrics': {'accuracy': 1.0}},
        headers=headers,
    )
    assert validated.status_code == 422


def test_simulation_is_model_backed_validated_and_never_persists(client, teacher_token):
    headers = {'Authorization': f'Bearer {teacher_token}'}
    student_id = client.app.state.test_student_id
    session_factory = client.app.state.test_session_factory
    with session_factory() as db:
        student = db.query(Student).filter_by(id=student_id).one()
        saved_state = (student.risk_level, student.risk_probability)
        baseline_features = student_features(student, db)
        expected_baseline = predict_risk(baseline_features)
        counts_before = (db.query(RiskPrediction).count(), db.query(RiskSnapshot).count())

    response = client.post('/api/v1/risk/simulate', json={'student_id': student_id, 'scenario': {'attendance': 95.0, 'assessment': 88.0}}, headers=headers)
    assert response.status_code == 200
    result = response.json()
    assert result['simulation_label'] == 'SIMULATION / WHAT-IF - NOT AN ACTUAL STUDENT PREDICTION'
    assert result['baseline_prediction']['risk_level'] == expected_baseline['risk_level']
    assert result['baseline_prediction']['class_probabilities'] == pytest.approx(expected_baseline['class_probabilities'])
    assert result['model_version'] == expected_baseline['model_version']
    assert result['simulation_timestamp']
    assert sum(result['baseline_class_probabilities'].values()) == pytest.approx(1.0)
    assert sum(result['simulated_class_probabilities'].values()) == pytest.approx(1.0)
    assert set(result['probability_deltas']) == set(result['baseline_class_probabilities'])
    assert {item['name'] for item in result['changed_features']} == {'attendance', 'assessment'}
    assert set(result['unchanged_features']) == set(FEATURES) - {'attendance', 'assessment'}
    assert result['simulated_prediction']['class_probabilities'] == pytest.approx(predict_risk({**baseline_features, 'attendance': 95.0, 'assessment': 88.0})['class_probabilities'])

    with session_factory() as db:
        student = db.query(Student).filter_by(id=student_id).one()
        assert (student.risk_level, student.risk_probability) == saved_state
        assert (db.query(RiskPrediction).count(), db.query(RiskSnapshot).count()) == counts_before


def test_simulator_rejects_unsupported_features_ranges_and_student_access(client, teacher_token, student_token):
    teacher_headers = {'Authorization': f'Bearer {teacher_token}'}
    student_headers = {'Authorization': f'Bearer {student_token}'}
    student_id = client.app.state.test_student_id
    assert client.post('/api/v1/risk/simulate', json={'student_id': student_id, 'scenario': {'fa1': 20}}, headers=teacher_headers).status_code == 422
    assert client.post('/api/v1/risk/simulate', json={'student_id': student_id, 'scenario': {'attendance': 90, 'fa1': 20}}, headers=teacher_headers).status_code == 422
    assert client.post('/api/v1/risk/simulate', json={'student_id': student_id, 'scenario': {'attendance': 101}}, headers=teacher_headers).status_code == 422
    assert client.post('/api/v1/risk/simulate', json={'student_id': 99999, 'scenario': {'attendance': 90}}, headers=teacher_headers).status_code == 404
    assert client.post('/api/v1/risk/simulate', json={'student_id': student_id, 'scenario': {'attendance': 90}}, headers=student_headers).status_code == 403
    assert client.post('/api/v1/models/registry', json={'model_version': 'student-model'}, headers=student_headers).status_code == 403
    assert client.get('/api/v1/models/registry', headers=student_headers).status_code == 403
    assert client.get('/api/v1/risk/data-quality', headers=student_headers).status_code == 403
    assert client.get('/api/v1/risk/transitions', headers=student_headers).status_code == 403


def test_supported_what_if_values_change_model_probabilities(client, teacher_token):
    headers = {'Authorization': f'Bearer {teacher_token}'}
    student_id = client.app.state.test_student_id
    responses = [client.post('/api/v1/risk/simulate', json={'student_id': student_id, 'scenario': {'attendance': value}}, headers=headers) for value in (0, 100)]
    assert all(response.status_code == 200 for response in responses)
    first, second = (response.json() for response in responses)
    assert first['simulated_class_probabilities'] != second['simulated_class_probabilities']


def test_data_quality_reports_database_counts_and_readiness_blockers(client, teacher_token):
    report = client.get('/api/v1/risk/data-quality', headers={'Authorization': f'Bearer {teacher_token}'})
    assert report.status_code == 200
    payload = report.json()
    assert payload['status'] in {'healthy', 'warning', 'critical'}
    assert payload['generated_at']
    assert payload['readiness']['training_ready'] is False
    assert payload['readiness']['blockers']
    assert payload['counts']['subject_records'] == 0
    assert payload['coverage']['fa1_percent'] is None
    assert payload['coverage']['fa2_percent'] is None
    assert payload['checks']['unmatched_student_rows'] == 0
    assert payload['checks']['unmatched_subject_rows'] == 0
    assert payload['checks']['temporal_alignment_problems'] == 0


@pytest.mark.parametrize(('previous_level', 'new_level'), [
    ('LOW', 'MEDIUM'), ('LOW', 'HIGH'), ('MEDIUM', 'HIGH'),
    ('HIGH', 'MEDIUM'), ('MEDIUM', 'LOW'), ('HIGH', 'LOW'),
])
def test_transition_detection_uses_saved_predictions_and_reports_insufficient_history(client, teacher_token, previous_level, new_level):
    headers = {'Authorization': f'Bearer {teacher_token}'}
    session_factory = client.app.state.test_session_factory
    changed_student_id = client.app.state.test_student_id
    insufficient_student_id = client.app.state.test_other_student_id
    from datetime import datetime
    with session_factory() as db:
        db.add_all([
            RiskPrediction(student_id=changed_student_id, risk_level=previous_level, probability=0.55, model_version='risk-old', prediction_timestamp=datetime(2026, 9, 1), input_features={}),
            RiskPrediction(student_id=changed_student_id, risk_level=new_level, probability=0.72, model_version='risk-current', prediction_timestamp=datetime(2026, 10, 1), input_features={}),
            AcademicMomentum(student_id=changed_student_id, metric='assessment', value=10, observed_at=datetime(2026, 9, 1)),
        ])
        db.commit()
    response = client.get('/api/v1/risk/transitions', headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload['history_status'] == 'available'
    transition = next(item for item in payload['transitions'] if item['student_id'] == changed_student_id)
    assert transition['previous_risk'] == previous_level
    assert transition['new_risk'] == new_level
    assert transition['probability_delta'] == pytest.approx(0.17)
    assert transition['model_version'] == 'risk-current'
    assert transition['recorded_at'].startswith('2026-10-01')
    assert transition['evidence']['previous_prediction_id']
    assert insufficient_student_id in payload['students_with_insufficient_history']


def test_transition_endpoint_explicitly_reports_insufficient_history(client, teacher_token):
    response = client.get('/api/v1/risk/transitions', headers={'Authorization': f'Bearer {teacher_token}'})
    assert response.status_code == 200
    payload = response.json()
    assert payload['history_status'] == 'insufficient_history'
    assert payload['transitions'] == []
