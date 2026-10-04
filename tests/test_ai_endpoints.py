import pandas as pd
import pytest

from ai.risk.features import FEATURES
from ai.risk.predict import predict
from ai.risk.train import train


def build_model(tmp_path):
    rows = []
    for index in range(48):
        high = index % 2 == 0
        row = {name: float(index % 5 + 1) for name in FEATURES}
        row.update({'attendance': 61 if high else 95, 'assessment': 45 if high else 88, 'current_gpa': 2 if high else 3.8, 'risk_label': 'HIGH' if high else 'LOW'})
        rows.append(row)
    source = tmp_path / 'features.csv'
    pd.DataFrame(rows).to_csv(source, index=False)
    artifact = tmp_path / 'model.joblib'
    train(source, artifact)
    return rows[0], artifact


def test_prediction_shap_and_intervention_review_flow(client, teacher_token, student_token, tmp_path, monkeypatch):
    features, artifact = build_model(tmp_path)
    monkeypatch.setattr('backend.app.main.settings.llm_model_name', 'mock-development')
    monkeypatch.setattr('backend.app.main.predict_risk', lambda item: predict(item, artifact))
    from ai.explainability.service import explain_student
    monkeypatch.setattr('backend.app.main.explain_student', lambda item, target_class=None: explain_student(item, artifact, target_class=target_class))
    teacher = {'Authorization': f'Bearer {teacher_token}'}
    student_headers = {'Authorization': f'Bearer {student_token}'}

    prediction = client.post('/api/v1/risk/predict', json={name: 0.0 for name in FEATURES}, headers=teacher)
    assert prediction.status_code == 200
    prediction_data = prediction.json()
    assert prediction_data['model_version'].startswith('risk-')
    assert prediction_data['risk_probability_semantics'] == 'P(risk_level)'
    assert prediction_data['risk_level_policy'] == 'argmax(class_probabilities)'
    assert prediction_data['risk_level'] == max(prediction_data['class_probabilities'], key=prediction_data['class_probabilities'].get)
    assert prediction_data['risk_probability'] == prediction_data['class_probabilities'][prediction_data['risk_level']]
    assert sum(prediction_data['class_probabilities'].values()) == pytest.approx(1.0)
    assert all(0 <= value <= 1 for value in prediction_data['class_probabilities'].values())
    current_student_payload = {name: 0.0 for name in FEATURES}
    prediction = client.post('/api/v1/risk/predict', json={**current_student_payload, 'student_id': client.app.state.test_student_id}, headers=teacher)
    assert prediction.status_code == 200
    prediction_data = prediction.json()
    student_data = client.get(f"/api/v1/students/{client.app.state.test_student_id}", headers=teacher).json()['student']
    assert student_data['risk_level'] == prediction_data['risk_level']
    assert student_data['risk_probability'] == prediction_data['risk_probability']
    dashboard_student = next(item for item in client.get('/api/v1/dashboard/teacher', headers=teacher).json()['students_needing_attention'] if item['id'] == client.app.state.test_student_id)
    assert dashboard_student['risk_level'] == prediction_data['risk_level']
    assert dashboard_student['risk_probability'] == prediction_data['risk_probability']
    student_detail = client.get(f"/api/v1/students/{client.app.state.test_student_id}", headers=teacher).json()
    assert all('risk_probability' not in snapshot for snapshot in student_detail['risk_history'])

    student_id = client.app.state.test_student_id
    explanation_response = client.get(f'/api/v1/students/{student_id}/shap', headers=teacher)
    assert explanation_response.status_code == 200
    explanation_data = explanation_response.json()
    assert len(explanation_data['explanation']['waterfall']) == len(FEATURES)
    assert explanation_data['explanation']['target_class'] == explanation_data['prediction']['risk_level']
    assert explanation_data['explanation']['target'] == f"P({explanation_data['prediction']['risk_level']})"
    assert explanation_data['explanation']['base_value'] + sum(explanation_data['explanation']['contributions'].values()) == pytest.approx(explanation_data['prediction']['risk_probability'], abs=1e-5)
    draft = client.post('/api/v1/interventions/generate', json={'student_id': student_id}, headers=teacher)
    assert draft.status_code == 201
    assert draft.json()['provider'] == 'development-template-not-an-llm'
    assert 'AI-GENERATED DRAFT - FACULTY REVIEW REQUIRED' in draft.json()['body']
    assert 'No institutional policy has been inferred' in draft.json()['body']
    risk_evidence = draft.json()['evidence']['risk_prediction']
    assert isinstance(risk_evidence['class_probabilities'], dict)
    assert isinstance(risk_evidence['risk_probability'], float)
    assert risk_evidence['risk_level'] == max(risk_evidence['class_probabilities'], key=risk_evidence['class_probabilities'].get)
    assert risk_evidence['risk_probability'] == risk_evidence['class_probabilities'][risk_evidence['risk_level']]
    assert draft.json()['evidence']['shap']['target_class'] == risk_evidence['risk_level']
    updated_student = client.get(f"/api/v1/students/{student_id}", headers=teacher).json()['student']
    assert updated_student['risk_level'] == risk_evidence['risk_level']
    assert updated_student['risk_probability'] == risk_evidence['risk_probability']

    edited = client.patch(f"/api/v1/interventions/{draft.json()['id']}", json={'title': 'Faculty support check-in', 'body': 'I would like to meet and review study strategies together.'}, headers=teacher)
    assert edited.status_code == 200
    approved = client.post(f"/api/v1/interventions/{draft.json()['id']}/approve", headers=teacher)
    assert approved.status_code == 200
    notices = client.get('/api/v1/notifications', headers=student_headers)
    assert notices.status_code == 200
    assert any(item['title'] == 'Faculty support check-in' for item in notices.json())


def test_current_risk_views_ignore_stale_seed_classifications(client, teacher_token, monkeypatch):
    fresh_prediction = {
        'risk_level': 'MEDIUM',
        'risk_probability': 0.7,
        'risk_probability_semantics': 'P(risk_level)',
        'risk_level_policy': 'argmax(class_probabilities)',
        'class_probabilities': {'HIGH': 0.2, 'LOW': 0.1, 'MEDIUM': 0.7},
        'model_version': 'risk-test',
    }
    monkeypatch.setattr('backend.app.main.predict_risk', lambda _: fresh_prediction)
    headers = {'Authorization': f'Bearer {teacher_token}'}
    seeded_student_id = client.app.state.test_student_id

    profile = client.get(f'/api/v1/students/{seeded_student_id}', headers=headers).json()['student']
    assert profile['risk_level'] == 'MEDIUM'
    assert profile['risk_probability'] == 0.7
    assert profile['class_probabilities'] == fresh_prediction['class_probabilities']

    directory = client.get('/api/v1/students?risk=MEDIUM&limit=100', headers=headers).json()
    assert {item['risk_level'] for item in directory['items']} == {'MEDIUM'}
    assert any(item['id'] == seeded_student_id for item in directory['items'])
    assert client.get('/api/v1/students?risk=HIGH&limit=100', headers=headers).json()['items'] == []

    dashboard = client.get('/api/v1/dashboard/teacher', headers=headers).json()
    assert dashboard['summary']['high_risk'] == 0
    assert dashboard['summary']['medium_risk'] == 2
    assert dashboard['summary']['low_risk'] == 0
    assert all(item['risk_level'] == 'MEDIUM' and item['risk_probability'] == 0.7 for item in dashboard['students_needing_attention'])

    monitoring = client.get('/api/v1/risk/monitoring', headers=headers).json()
    assert monitoring['distribution'] == {'HIGH': 0, 'MEDIUM': 2, 'LOW': 0}
    assert 'Historical saved class labels' in monitoring['history_note']
    assert all('risk_probability' not in snapshot for snapshot in monitoring['history'])

    monkeypatch.setattr('backend.app.main.student_features', lambda student, db: {name: 0.0 for name in FEATURES} | {'attendance_change': -25.0})
    warnings = client.get('/api/v1/early-warnings', headers=headers).json()
    assert warnings
    assert all(item['risk_level'] == 'MEDIUM' for item in warnings)

    report = client.get('/api/v1/reports/export.csv?report_type=risk', headers=headers).text
    assert 'T-001,Student One,,MEDIUM,0.7' in report


def test_high_risk_demo_explains_the_same_canonical_class_and_is_read_only(client, teacher_token, monkeypatch):
    prediction = {
        'risk_level': 'HIGH',
        'risk_probability': 0.81,
        'class_probabilities': {'HIGH': 0.81, 'MEDIUM': 0.15, 'LOW': 0.04},
        'model_version': 'risk-demo-test',
        'risk_probability_semantics': 'P(risk_level)',
        'risk_level_policy': 'argmax(class_probabilities)',
    }
    monkeypatch.setattr('backend.app.main.predict_risk', lambda _: prediction)
    monkeypatch.setattr('backend.app.main.explain_student', lambda _, target_class=None: {
        'target': f'P({target_class})', 'target_class': target_class, 'model_version': 'risk-demo-test',
        'contributions': {'attendance': 0.2}, 'feature_values': {'attendance': 61.0},
        'waterfall': [{'feature': 'attendance', 'value': 61.0, 'contribution': 0.2}],
    })
    headers = {'Authorization': f'Bearer {teacher_token}'}
    before = client.get('/api/v1/students/1', headers=headers).json()['student']
    response = client.get('/api/v1/risk/high-risk-demo', headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data['high_risk_available'] is True
    assert data['prediction']['risk_level'] == 'HIGH'
    assert data['prediction']['risk_probability'] == data['prediction']['class_probabilities']['HIGH']
    assert data['explanation']['target_class'] == data['prediction']['risk_level']
    assert data['explanation']['target'] == 'P(HIGH)'
    assert data['student']['student_id'] == 'T-001'
    after = client.get('/api/v1/students/1', headers=headers).json()['student']
    assert after == before


def test_high_risk_demo_has_deterministic_fallback_without_relabeling(client, teacher_token, monkeypatch):
    prediction = {
        'risk_level': 'MEDIUM',
        'risk_probability': 0.7,
        'class_probabilities': {'HIGH': 0.2, 'MEDIUM': 0.7, 'LOW': 0.1},
        'model_version': 'risk-demo-test',
        'risk_probability_semantics': 'P(risk_level)',
        'risk_level_policy': 'argmax(class_probabilities)',
    }
    monkeypatch.setattr('backend.app.main.predict_risk', lambda _: prediction)
    monkeypatch.setattr('backend.app.main.explain_student', lambda _, target_class=None: {'target': f'P({target_class})', 'target_class': target_class})
    response = client.get('/api/v1/risk/high-risk-demo', headers={'Authorization': f'Bearer {teacher_token}'})
    assert response.status_code == 200
    data = response.json()
    assert data['high_risk_available'] is False
    assert 'highest P(HIGH)' in data['selection_note']
    assert data['prediction']['risk_level'] == 'MEDIUM'
    assert data['explanation']['target'] == 'P(MEDIUM)'


def test_high_risk_demo_is_teacher_only(client, student_token):
    assert client.get('/api/v1/risk/high-risk-demo', headers={'Authorization': f'Bearer {student_token}'}).status_code == 403


def test_read_only_student_explanation_uses_canonical_shap_target(client, teacher_token, student_token, monkeypatch):
    prediction = {
        'risk_level': 'MEDIUM',
        'risk_probability': 0.72,
        'risk_probability_semantics': 'P(risk_level)',
        'risk_level_policy': 'argmax(class_probabilities)',
        'class_probabilities': {'HIGH': 0.2, 'MEDIUM': 0.72, 'LOW': 0.08},
        'model_version': 'risk-read-only-test',
    }
    monkeypatch.setattr('backend.app.main.predict_risk', lambda _: prediction)
    monkeypatch.setattr('backend.app.main.explain_student', lambda _, target_class=None: {'target': f'P({target_class})', 'target_class': target_class})
    teacher = {'Authorization': f'Bearer {teacher_token}'}
    student = {'Authorization': f'Bearer {student_token}'}
    before = client.get('/api/v1/students/1', headers=teacher).json()['student']
    response = client.get('/api/v1/students/1/explanation', headers=teacher)
    assert response.status_code == 200
    data = response.json()
    assert data['prediction']['risk_level'] == 'MEDIUM'
    assert data['explanation']['target_class'] == 'MEDIUM'
    assert data['explanation']['target'] == 'P(MEDIUM)'
    assert client.get('/api/v1/students/1/explanation', headers=student).status_code == 403
    assert client.get('/api/v1/students/1/explanation').status_code == 401
    assert client.get('/api/v1/students/1', headers=teacher).json()['student'] == before