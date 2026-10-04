import hashlib
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pytest
from sklearn.preprocessing import LabelEncoder

from ai.risk.features import FEATURES
from ai.risk.predict import DEFAULT_ARTIFACT, load_artifact
from backend.app.models import AuditLog, ModelDeploymentEvent, ModelDeploymentState, ModelRegistryEntry, RiskPrediction, User


class FixturePipeline:
    def __init__(self, features):
        self.feature_names_in_ = np.asarray(features, dtype=object)
        self.n_features_in_ = len(features)
        self.classes_ = np.asarray([0, 1, 2])

    def predict_proba(self, frame):
        return np.tile(np.asarray([0.2, 0.3, 0.5]), (len(frame), 1))


def create_candidate(client, monkeypatch, artifact_directory: Path, *, features=None, version='local-fixture-v1'):
    selected_features = list(features or FEATURES)
    artifact_directory.mkdir(parents=True, exist_ok=True)
    metrics = {
        'validation': {'sample_count': 30, 'accuracy': 0.8},
        'test': {'sample_count': 30, 'accuracy': 0.75, 'macro_f1': 0.72, 'per_class': {'HIGH': {'support': 10}, 'LOW': {'support': 10}, 'MEDIUM': {'support': 10}}, 'confusion_matrix': [[8, 1, 1], [1, 8, 1], [1, 1, 8]]},
        'feature_importance': {'split': 'validation'},
        'subgroup_evaluation': {'split': 'test'},
    }
    metadata = {
        'model_version': version,
        'dataset_id': 'fixture-dataset',
        'dataset_fingerprint': 'c' * 64,
        'feature_contract': selected_features,
        'feature_contract_version': 'risk-features-v1',
        'target_definition': 'Fixture-only independent target',
        'aggregation_strategy': 'fixture-compatible-input',
        'algorithm': 'logistic_regression',
        'validation_metrics': metrics['validation'],
        'test_metrics': metrics['test'],
        'feature_importance': metrics['feature_importance'],
        'subgroup_evaluation': metrics['subgroup_evaluation'],
    }
    path = artifact_directory / f'{version}.joblib'
    joblib.dump({
        'pipeline': FixturePipeline(selected_features),
        'label_encoder': LabelEncoder().fit(['HIGH', 'LOW', 'MEDIUM']),
        'metadata': metadata,
        'feature_contract': selected_features,
        'background': np.zeros((1, len(selected_features))),
    }, path)
    artifact_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    with client.app.state.test_session_factory() as db:
        teacher = db.query(User).filter_by(email='teacher@example.com').one()
        entry = ModelRegistryEntry(
            model_id=version,
            model_version=version,
            model_type='classification',
            feature_schema=selected_features,
            feature_contract_version='risk-features-v1',
            training_dataset_version='fixture-v1',
            training_dataset_hash='c' * 64,
            algorithm='logistic_regression',
            training_timestamp=datetime(2026, 1, 1),
            validation_metrics=metrics,
            artifact_identifier=path.name,
            artifact_hash=artifact_hash,
            status='candidate',
            deployment_status='SHADOW',
            created_by_user_id=teacher.id,
            dataset_id='fixture-dataset',
            dataset_version='fixture-v1',
            dataset_fingerprint='c' * 64,
            target_definition=metadata['target_definition'],
            aggregation_strategy=metadata['aggregation_strategy'],
            validation_status='passed',
            approval_status='approved',
            approved_by_user_id=teacher.id,
            approved_at=datetime(2026, 1, 2),
        )
        db.add(entry)
        db.commit()
        entry_id = entry.id
    monkeypatch.setattr('backend.app.main.CANDIDATE_ARTIFACT_DIRECTORY', artifact_directory)
    monkeypatch.setattr('backend.app.main.build_phase3_dataset', lambda *args, **kwargs: {
        'dataset_id': 'fixture-dataset',
        'dataset_version': 'fixture-v1',
        'dataset_fingerprint': 'c' * 64,
        'readiness': {'training_ready': True, 'blockers': []},
    })
    return entry_id, version, artifact_hash


def auth(token):
    return {'Authorization': f'Bearer {token}'}


def test_local_deploy_switches_inference_and_rollback_restores_verified_fallback(client, teacher_token, student_token, monkeypatch, tmp_path):
    headers = auth(teacher_token)
    assert client.get('/api/v1/models/deployments', headers=auth(student_token)).status_code == 403
    production_hash = hashlib.sha256(DEFAULT_ARTIFACT.read_bytes()).hexdigest()
    production_version = load_artifact()['metadata']['model_version']
    comparison_id, _, _ = create_candidate(
        client, monkeypatch, tmp_path / 'candidate-artifacts',
        features=['fa1_mean', 'fa2_mean'], version='incompatible-comparison-fixture-v1',
    )
    incompatible_comparison = client.get('/api/v1/ml/phase3/compare', headers=auth(teacher_token))
    assert incompatible_comparison.status_code == 200
    comparison = incompatible_comparison.json()
    assert comparison['status'] == 'unavailable'
    assert comparison['comparison']['winner'] is None
    assert comparison['comparison']['common_test_set'] is None
    assert comparison['comparison']['compatible'] is False
    assert comparison['comparison']['feature_contract']['compatible'] is False
    assert comparison['comparison']['dataset_identity']['compatible'] is False
    assert comparison['comparison']['dataset_identity']['same_temporal_test_rows_verified'] is False
    assert any('feature contracts' in blocker for blocker in comparison['comparison']['blockers'])
    assert any('demo/synthetic' in blocker for blocker in comparison['comparison']['blockers'])
    assert comparison['production']['metrics'] is not None
    assert comparison['candidate_test_evaluation']['per_class']
    assert comparison['candidate_test_evaluation']['confusion_matrix']
    assert comparison['candidate_test_provenance']['dataset_hash'] == 'c' * 64
    entry_id, candidate_version, candidate_hash = create_candidate(client, monkeypatch, tmp_path / 'candidate-artifacts')

    deployed = client.post(f'/api/v1/models/registry/{entry_id}/promote', json={
        'explicit_approval': True,
        'approval_note': 'Deploy the verified fixture to the local adapter.',
    }, headers=headers)
    assert deployed.status_code == 200, deployed.text
    assert deployed.json()['deployment_target'] == 'LOCAL'
    assert deployed.json()['active_model_version'] == candidate_version

    prediction = client.post('/api/v1/risk/predict', json={
        'attendance': 80, 'assessment': 70, 'previous_gpa': 3, 'current_gpa': 3,
        'assignments_completed': 4, 'activity_per_week': 3, 'missing_submissions': 0,
        'attendance_change': 0, 'assessment_change': 0, 'momentum_score': 0,
    }, headers=headers)
    assert prediction.status_code == 200, prediction.text
    assert prediction.json()['model_version'] == candidate_version

    history = client.get('/api/v1/models/deployments', headers=headers).json()
    assert history['active']['model_version'] == candidate_version
    promote_event = history['history'][0]
    assert promote_event['event'] == 'PROMOTE'
    assert promote_event['status'] == 'succeeded'
    assert promote_event['previous_version'] == production_version
    assert promote_event['new_version'] == candidate_version
    assert promote_event['artifact_hash'] == candidate_hash
    assert promote_event['actor_role'] == 'TEACHER'
    assert promote_event['dataset_hash'] == 'c' * 64
    assert promote_event['feature_contract'] == list(FEATURES)
    assert promote_event['evaluation_reference']['test']['sample_count'] == 30
    candidate_path = tmp_path / 'candidate-artifacts' / 'local-fixture-v1.joblib'
    candidate_path.write_bytes(b'changed after approval')
    unsafe_prediction = client.post('/api/v1/risk/predict', json={
        'attendance': 80, 'assessment': 70, 'previous_gpa': 3, 'current_gpa': 3,
        'assignments_completed': 4, 'activity_per_week': 3, 'missing_submissions': 0,
        'attendance_change': 0, 'assessment_change': 0, 'momentum_score': 0,
    }, headers=headers)
    assert unsafe_prediction.status_code == 503
    assert 'SHA-256' in unsafe_prediction.json()['detail']

    rolled_back = client.post(f'/api/v1/models/registry/{entry_id}/rollback', json={
        'explicit_approval': True,
        'rollback_note': 'Restore the previously verified production fallback.',
    }, headers=headers)
    assert rolled_back.status_code == 200, rolled_back.text
    assert rolled_back.json()['active_model_version'] == production_version
    assert rolled_back.json()['rollback_of_event_id'] == promote_event['id']

    fallback_prediction = client.post('/api/v1/risk/predict', json={
        'attendance': 80, 'assessment': 70, 'previous_gpa': 3, 'current_gpa': 3,
        'assignments_completed': 4, 'activity_per_week': 3, 'missing_submissions': 0,
        'attendance_change': 0, 'assessment_change': 0, 'momentum_score': 0,
    }, headers=headers)
    assert fallback_prediction.status_code == 200
    assert fallback_prediction.json()['model_version'] == production_version
    assert hashlib.sha256(DEFAULT_ARTIFACT.read_bytes()).hexdigest() == production_hash
    final_history = client.get('/api/v1/models/deployments', headers=headers).json()
    assert final_history['active']['model_version'] == production_version
    assert [row['event'] for row in final_history['history'][:2]] == ['ROLLBACK', 'PROMOTE']
    assert final_history['history'][0]['rollback_of_event_id'] == promote_event['id']

    with client.app.state.test_session_factory() as db:
        events = db.query(ModelDeploymentEvent).order_by(ModelDeploymentEvent.id).all()
        audits = db.query(AuditLog).filter(AuditLog.resource_type == 'model_deployment').all()
        state = db.query(ModelDeploymentState).one()
        assert state.active_model_version == production_version
        assert len(events) == len(audits) == 2
        with pytest.raises(ValueError, match='immutable'):
            events[0].reason = 'attempt mutation'
            db.flush()


def test_unsafe_feature_contract_is_blocked_without_changing_active_model(client, teacher_token, monkeypatch, tmp_path):
    headers = auth(teacher_token)
    production_version = load_artifact()['metadata']['model_version']
    entry_id, _, _ = create_candidate(client, monkeypatch, tmp_path / 'candidate-artifacts', features=['fa1_mean', 'fa2_mean'])
    result = client.post(f'/api/v1/models/registry/{entry_id}/promote', json={
        'explicit_approval': True,
        'approval_note': 'Reject this incompatible fixture contract.',
    }, headers=headers)
    assert result.status_code == 409
    assert any('incompatible with the live prediction input contract' in item for item in result.json()['detail']['blockers'])
    history = client.get('/api/v1/models/deployments', headers=headers).json()
    assert history['active']['model_version'] == production_version
    assert history['history'][0]['status'] == 'blocked'
    assert history['history'][0]['previous_version'] == production_version
    assert history['history'][0]['new_version'] == production_version


def test_candidate_rejection_is_audited_and_cannot_be_deployed(client, teacher_token, monkeypatch, tmp_path):
    headers = auth(teacher_token)
    entry_id, candidate_version, _ = create_candidate(client, monkeypatch, tmp_path / 'candidate-artifacts')
    rejected = client.post(f'/api/v1/models/registry/{entry_id}/reject', json={
        'rejection_reason': 'Fixture review found a documented policy concern.',
    }, headers=headers)
    assert rejected.status_code == 200
    assert rejected.json()['status'] == 'rejected'
    result = client.post(f'/api/v1/models/registry/{entry_id}/promote', json={
        'explicit_approval': True,
        'approval_note': 'Attempt rejected fixture deployment.',
    }, headers=headers)
    assert result.status_code == 409
    with client.app.state.test_session_factory() as db:
        entry = db.query(ModelRegistryEntry).filter_by(model_version=candidate_version).one()
        assert entry.rejected_by_user_id is not None
        assert entry.rejected_at is not None
        assert entry.rejection_reason
        assert db.query(AuditLog).filter_by(action='model.candidate.rejected').count() == 1


def test_rollback_is_blocked_without_verified_prior_deployment_and_routes_are_teacher_only(client, teacher_token, student_token):
    payload = {'explicit_approval': True, 'rollback_note': 'No prior deployment fixture exists.'}
    blocked = client.post('/api/v1/models/registry/1/rollback', json=payload, headers=auth(teacher_token))
    assert blocked.status_code == 404
    assert client.get('/api/v1/models/deployments', headers=auth(student_token)).status_code == 403
    assert client.get('/api/v1/models/deployments', headers=auth(teacher_token)).status_code == 200


def test_artifact_hash_mismatch_blocks_deployment_and_is_recorded(client, teacher_token, monkeypatch, tmp_path):
    headers = auth(teacher_token)
    production_version = load_artifact()['metadata']['model_version']
    artifact_directory = tmp_path / 'candidate-artifacts'
    entry_id, _, _ = create_candidate(client, monkeypatch, artifact_directory)
    (artifact_directory / 'local-fixture-v1.joblib').write_bytes(b'tampered before deployment')

    response = client.post(f'/api/v1/models/registry/{entry_id}/promote', json={
        'explicit_approval': True,
        'approval_note': 'Attempt to deploy a changed fixture artifact.',
    }, headers=headers)
    assert response.status_code == 409
    assert any('SHA-256' in blocker for blocker in response.json()['detail']['blockers'])
    history = client.get('/api/v1/models/deployments', headers=headers).json()
    assert history['active']['model_version'] == production_version
    assert history['history'][0]['status'] == 'blocked'
    assert 'SHA-256' in history['history'][0]['reason']


def test_rollback_must_name_the_active_local_registry_entry(client, teacher_token, monkeypatch, tmp_path):
    headers = auth(teacher_token)
    artifact_directory = tmp_path / 'candidate-artifacts'
    active_id, active_version, _ = create_candidate(client, monkeypatch, artifact_directory)
    other_id, other_version, _ = create_candidate(client, monkeypatch, artifact_directory, version='other-local-fixture-v1')
    deployed = client.post(f'/api/v1/models/registry/{active_id}/promote', json={
        'explicit_approval': True,
        'approval_note': 'Deploy the candidate used for this rollback test.',
    }, headers=headers)
    assert deployed.status_code == 200, deployed.text

    response = client.post(f'/api/v1/models/registry/{other_id}/rollback', json={
        'explicit_approval': True,
        'rollback_note': 'Attempt rollback using a non-active candidate ID.',
    }, headers=headers)
    assert response.status_code == 409
    assert 'not the active local deployment' in response.json()['detail']['blockers'][0]
    history = client.get('/api/v1/models/deployments', headers=headers).json()
    assert history['active']['model_version'] == active_version
    assert history['history'][0]['candidate_version'] == other_version
    assert history['history'][0]['status'] == 'blocked'


def test_prediction_transitions_include_student_probability_and_model_provenance(client, teacher_token, student_token):
    student_id = client.app.state.test_student_id
    with client.app.state.test_session_factory() as db:
        db.add_all([
            RiskPrediction(
                student_id=student_id,
                risk_level='LOW',
                probability=0.61,
                model_version='risk-before',
                prediction_timestamp=datetime(2026, 1, 1),
                input_features={},
            ),
            RiskPrediction(
                student_id=student_id,
                risk_level='HIGH',
                probability=0.74,
                model_version='risk-after',
                prediction_timestamp=datetime(2026, 2, 1),
                input_features={},
            ),
        ])
        db.commit()

    teacher_response = client.get('/api/v1/risk/transitions', headers=auth(teacher_token))
    assert teacher_response.status_code == 200
    transition = next(row for row in teacher_response.json()['transitions'] if row['student_id'] == student_id)
    assert transition['student_name'] == 'Student One'
    assert transition['previous_risk'] == 'LOW'
    assert transition['new_risk'] == 'HIGH'
    assert transition['previous_probability'] == pytest.approx(0.61)
    assert transition['new_probability'] == pytest.approx(0.74)
    assert transition['probability_delta'] == pytest.approx(0.13)
    assert transition['previous_model_version'] == 'risk-before'
    assert transition['model_version'] == 'risk-after'
    assert transition['recorded_at'].startswith('2026-02-01')
    assert client.get('/api/v1/risk/transitions', headers=auth(student_token)).status_code == 403


def test_governance_audit_endpoint_is_teacher_only_and_empty_state_is_explicit(client, teacher_token, student_token):
    response = client.get('/api/v1/ml/phase3/audit?limit=10', headers=auth(teacher_token))
    assert response.status_code == 200
    assert isinstance(response.json()['items'], list)
    assert client.get('/api/v1/ml/phase3/audit', headers=auth(student_token)).status_code == 403
