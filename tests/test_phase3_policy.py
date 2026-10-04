from backend.app.models import AuditLog, Phase3PolicyApproval


def auth(token):
    return {'Authorization': f'Bearer {token}'}


def test_phase3_policy_requires_explicit_teacher_approval_and_does_not_clear_data_blockers(client, teacher_token, student_token):
    teacher = auth(teacher_token)
    student = auth(student_token)

    initial = client.get('/api/v1/ml/phase3/policy', headers=teacher)
    assert initial.status_code == 200
    assert initial.json()['status'] == 'unapproved'
    assert initial.json()['approved_policy'] is None
    assert client.get('/api/v1/ml/phase3/policy', headers=student).status_code == 403

    payload = {
        'explicit_approval': True,
        'aggregation_strategy': 'equal_subject_mean',
        'feature_contract': ['fa1_mean', 'fa2_mean'],
        'approval_note': 'Approve the named aggregation and feature contract for Phase 3 use.',
    }
    denied = client.post('/api/v1/ml/phase3/policy/approve', json={**payload, 'explicit_approval': False}, headers=teacher)
    assert denied.status_code == 422
    assert client.post('/api/v1/ml/phase3/policy/approve', json=payload, headers=student).status_code == 403

    approved = client.post('/api/v1/ml/phase3/policy/approve', json=payload, headers=teacher)
    assert approved.status_code == 200, approved.text
    assert approved.json()['status'] == 'approved'
    assert approved.json()['approved_policy']['feature_contract'] == ['fa1_mean', 'fa2_mean']
    assert approved.json()['approved_policy']['approved_by_user_id']
    assert approved.json()['approved_policy']['approved_at']

    readiness = client.get('/api/v1/ml/phase3/readiness', headers=teacher)
    assert readiness.status_code == 200
    assert readiness.json()['readiness']['training_ready'] is False
    assert readiness.json()['readiness']['evidence']['aggregation_approved'] is True
    assert readiness.json()['readiness']['evidence']['feature_contract_approved'] is True
    assert '0 independent outcomes available.' in readiness.json()['readiness']['blockers']

    training = client.post('/api/v1/ml/phase3/train', json={
        'aggregation_strategy': 'equal_subject_mean',
        'feature_contract': ['fa1_mean', 'fa2_mean'],
    }, headers=teacher)
    assert training.status_code == 409
    assert '0 independent outcomes available.' in training.json()['detail']['blockers']
    assert client.get('/api/v1/ml/phase3/candidate', headers=teacher).json()['candidate'] is None

    with client.app.state.test_session_factory() as db:
        approval = db.query(Phase3PolicyApproval).one()
        event = db.query(AuditLog).filter_by(action='phase3.policy.approved').one()
        assert approval.approved_by_user_id == event.actor_user_id
        assert event.detail['reason'] == payload['approval_note']
        assert event.detail['previous_state'] == {'status': 'unapproved'}
        assert event.detail['new_state']['feature_contract'] == payload['feature_contract']
        assert approval.id == int(event.resource_id)
