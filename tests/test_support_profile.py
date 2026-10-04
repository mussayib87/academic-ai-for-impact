from backend.app.models import InterventionDraft, RiskPrediction, RiskSnapshot


def test_support_profile_and_manual_support_action(client, teacher_token, monkeypatch):
    prediction = {
        'risk_level': 'HIGH',
        'risk_probability': 0.82,
        'risk_probability_semantics': 'P(risk_level)',
        'risk_level_policy': 'argmax(class_probabilities)',
        'class_probabilities': {'HIGH': 0.82, 'MEDIUM': 0.13, 'LOW': 0.05},
        'model_version': 'risk-test',
        'prediction_timestamp': '2026-01-01T12:00:00+00:00',
    }
    monkeypatch.setattr('backend.app.main.predict_risk', lambda _: prediction)
    monkeypatch.setattr('backend.app.main.explain_student', lambda _, target_class=None: {
        'summary': ['attendance decline', 'assessment decline'],
        'target_class': target_class,
        'target': f'P({target_class})',
        'contributions': {'attendance': 0.21, 'assessment': 0.15},
        'base_value': 0.1,
        'model_version': 'risk-test',
    })

    headers = {'Authorization': f'Bearer {teacher_token}'}
    student_id = client.app.state.test_student_id

    profile = client.get(f'/api/v1/students/{student_id}/support-profile', headers=headers)
    assert profile.status_code == 200, profile.text
    body = profile.json()
    assert body['student']['id'] == student_id
    assert body['risk']['level'] == 'HIGH'
    assert body['risk']['probability'] == 0.82
    assert body['risk_evidence']
    assert body['recommended_actions']

    action = client.post(
        f'/api/v1/students/{student_id}/support-actions',
        json={'title': 'Attendance review', 'action_type': 'ATTENDANCE_REVIEW', 'due_date': '2026-02-01T00:00:00+00:00'},
        headers=headers,
    )
    assert action.status_code == 201, action.text
    action_body = action.json()
    assert action_body['student_id'] == student_id
    assert action_body['status'] == 'PENDING_FACULTY_REVIEW'

    follow_up = client.post(
        f"/api/v1/interventions/{client.app.state.test_student_id}/follow-up",
        json={'assigned_to': 'teacher@example.com', 'scheduled_date': '2026-02-05T00:00:00+00:00', 'notes': 'Review follow-up with student.'},
        headers=headers,
    )
    assert follow_up.status_code == 200, follow_up.text
    assert follow_up.json()['status'] == 'SCHEDULED'


def test_invalid_generated_draft_is_not_persisted_and_manual_action_still_works(client, teacher_token, monkeypatch):
    prediction = {
        'risk_level': 'MEDIUM',
        'risk_probability': 0.6,
        'class_probabilities': {'HIGH': 0.1, 'MEDIUM': 0.6, 'LOW': 0.3},
        'model_version': 'risk-test',
        'prediction_timestamp': '2026-01-01T12:00:00+00:00',
    }
    monkeypatch.setattr('backend.app.main.predict_risk', lambda _: prediction)
    monkeypatch.setattr('backend.app.main.explain_student', lambda _, target_class=None: {
        'summary': ['Assessment increased the predicted risk.'],
        'target_class': target_class,
        'contributions': {'assessment': 0.2},
        'feature_values': {'assessment': 68.0},
    })
    monkeypatch.setattr('backend.app.main.retrieve', lambda _: {
        'matched': False,
        'sources': [],
        'message': 'No institutional policy has been inferred. No verified institutional resource is currently configured.',
    })

    class InvalidDraftProvider:
        provider_name = 'ollama-local'

        @staticmethod
        def generate_intervention(context):
            return (
                'AI-GENERATED DRAFT - FACULTY REVIEW REQUIRED\n'
                'OBSERVATIONS:\nCurrent risk is MEDIUM. There are ongoing fluctuations in attendance '
                'and assessment. The student has sustained risk. Assignments reduced risk.\n'
                'RECOMMENDATIONS:\nConsider discussing assignment planning.'
            )

    monkeypatch.setattr('backend.app.main.build_provider', lambda _: InvalidDraftProvider())
    headers = {'Authorization': f'Bearer {teacher_token}'}
    factory = client.app.state.test_session_factory

    with factory() as db:
        before_counts = (
            db.query(InterventionDraft).count(),
            db.query(RiskSnapshot).count(),
            db.query(RiskPrediction).count(),
        )

    response = client.post(
        '/api/v1/interventions/generate',
        json={'student_id': client.app.state.test_student_id},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'INTERVENTION_EVIDENCE_VALIDATION_FAILED'
    assert any('attendance momentum' in issue for issue in response.json()['detail']['issues'])
    with factory() as db:
        after_counts = (
            db.query(InterventionDraft).count(),
            db.query(RiskSnapshot).count(),
            db.query(RiskPrediction).count(),
        )
    assert after_counts == before_counts

    manual_action = client.post(
        f"/api/v1/students/{client.app.state.test_student_id}/support-actions",
        json={'title': 'Faculty check-in', 'action_type': 'FACULTY_CHECK_IN'},
        headers=headers,
    )
    assert manual_action.status_code == 201, manual_action.text
    assert manual_action.json()['status'] == 'PENDING_FACULTY_REVIEW'


def test_support_follow_up_transition_and_effectiveness(client, teacher_token, monkeypatch):
    prediction = {
        'risk_level': 'HIGH',
        'risk_probability': 0.82,
        'risk_probability_semantics': 'P(risk_level)',
        'risk_level_policy': 'argmax(class_probabilities)',
        'class_probabilities': {'HIGH': 0.82, 'MEDIUM': 0.13, 'LOW': 0.05},
        'model_version': 'risk-test',
        'prediction_timestamp': '2026-01-01T12:00:00+00:00',
    }
    monkeypatch.setattr('backend.app.main.predict_risk', lambda _: prediction)
    monkeypatch.setattr('backend.app.main.explain_student', lambda _, target_class=None: {
        'summary': ['attendance decline', 'assessment decline'],
        'target_class': target_class,
        'target': f'P({target_class})',
        'contributions': {'attendance': 0.21, 'assessment': 0.15},
        'base_value': 0.1,
        'model_version': 'risk-test',
    })

    headers = {'Authorization': f'Bearer {teacher_token}'}
    student_id = client.app.state.test_student_id

    follow_up = client.post(
        f'/api/v1/interventions/{student_id}/follow-up',
        json={'assigned_to': 'teacher@example.com', 'scheduled_date': '2026-02-05T00:00:00+00:00', 'notes': 'Review follow-up with student.'},
        headers=headers,
    )
    assert follow_up.status_code == 200, follow_up.text
    follow_up_id = follow_up.json()['id']

    completed = client.patch(
        f'/api/v1/support-follow-ups/{follow_up_id}',
        json={'action': 'complete', 'outcome': 'Met with student and agreed on a revised study plan.'},
        headers=headers,
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()['status'] == 'COMPLETED'

    effectiveness = client.get(f'/api/v1/students/{student_id}/support-effectiveness', headers=headers)
    assert effectiveness.status_code == 200, effectiveness.text
    assert 'summary' in effectiveness.json()

    plan = client.post(
        f'/api/v1/students/{student_id}/support-plan',
        json={'summary': 'Revised support plan after check-in', 'plan': [{'title': 'Study plan', 'action_type': 'MENTORING'}]},
        headers=headers,
    )
    assert plan.status_code == 200, plan.text
    assert plan.json()['version'] == 1


def test_student_cannot_view_another_students_support_profile(client, teacher_token, student_token):
    headers_teacher = {'Authorization': f'Bearer {teacher_token}'}
    headers_student = {'Authorization': f'Bearer {student_token}'}
    other_student_id = client.app.state.test_other_student_id

    response = client.get(f'/api/v1/students/{other_student_id}/support-profile', headers=headers_student)
    assert response.status_code == 404


def test_support_resources_communicate_missing_verified_sources(client, student_token):
    headers = {'Authorization': f'Bearer {student_token}'}
    response = client.get('/api/v1/support/resources', headers=headers)
    assert response.status_code == 200, response.text
    assert 'No verified institutional resource is currently configured.' in response.json()['message']
