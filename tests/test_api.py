def auth(token):
    return {'Authorization': f'Bearer {token}'}


def test_login_me_and_invalid_credentials(client):
    response = client.post('/api/v1/auth/login', json={'email': 'teacher@example.com', 'password': 'teacher-pass'})
    assert response.status_code == 200
    assert client.get('/api/v1/me', headers=auth(response.json()['access_token'])).json()['role'] == 'TEACHER'
    assert client.post('/api/v1/auth/login', json={'email': 'teacher@example.com', 'password': 'wrong'}).status_code == 401
    assert client.get('/api/v1/me').status_code == 401


def test_teacher_authorization_and_student_isolation(client, teacher_token, student_token):
    teacher = auth(teacher_token)
    student = auth(student_token)
    assert client.get('/api/v1/dashboard/teacher', headers=teacher).status_code == 200
    assert client.get('/api/v1/dashboard/teacher', headers=student).status_code == 403
    student_dashboard = client.get('/api/v1/dashboard/student', headers=student)
    assert student_dashboard.status_code == 200
    assert 'risk_level' not in student_dashboard.json()['student']
    assert client.get('/api/v1/assignments', headers=student).status_code == 200
    own_id = client.get('/api/v1/students/me', headers=student).json()['id']
    own = client.get(f'/api/v1/students/{own_id}', headers=student)
    assert own.status_code == 200
    assert 'risk_level' not in own.json()['student']
    other_id = client.app.state.test_other_student_id
    assert client.get(f'/api/v1/students/{other_id}', headers=student).status_code == 404
    assert client.get(f'/api/v1/students/{other_id}', headers=teacher).status_code == 200
    assert client.get('/api/v1/students').status_code == 401


def test_teacher_creates_assignment_and_student_cannot(client, teacher_token, student_token):
    payload = {
        'title': 'Reflection',
        'subject': 'Academic Foundations',
        'section': 'A',
        'status': 'active',
        'max_marks': 20,
        'allowed_file_types': ['.txt'],
        'max_file_size': 2048,
    }
    assert client.post('/api/v1/assignments', json=payload, headers=auth(student_token)).status_code == 403
    created = client.post('/api/v1/assignments', json=payload, headers=auth(teacher_token))
    assert created.status_code == 201
    assert created.json()['title'] == 'Reflection'


def test_submission_upload_validation_grading_and_student_feedback(client, teacher_token, student_token):
    payload = {'title': 'Reflection', 'subject': 'Academic Foundations', 'section': 'A', 'status': 'active', 'max_marks': 20, 'allowed_file_types': ['.txt'], 'max_file_size': 2048}
    assignment = client.post('/api/v1/assignments', json=payload, headers=auth(teacher_token)).json()
    refused = client.post('/api/v1/submissions', data={'assignment_id': assignment['id']}, files={'file': ('run.exe', b'no execution')}, headers=auth(student_token))
    assert refused.status_code == 400
    submitted = client.post('/api/v1/submissions', data={'assignment_id': assignment['id']}, files={'file': ('work.txt', b'finished')}, headers=auth(student_token))
    assert submitted.status_code == 201
    submission_id = submitted.json()['id']
    versions = client.get(f'/api/v1/submissions/{submission_id}/versions', headers=auth(student_token))
    assert versions.status_code == 200
    assert versions.json()[0]['version_number'] == 1
    rubric = client.post(f"/api/v1/assignments/{assignment['id']}/rubric", json={'title': 'Reflection rubric', 'criteria': [{'name': 'Reasoning', 'maximum_score': 12}, {'name': 'Clarity', 'maximum_score': 8}]}, headers=auth(teacher_token))
    assert rubric.status_code == 201
    rubric_scores = {rubric.json()['criteria'][0]['id']: 10, rubric.json()['criteria'][1]['id']: 8}
    graded = client.patch(f'/api/v1/submissions/{submission_id}/grade', json={'feedback': 'Clear reasoning.', 'rubric_scores': rubric_scores}, headers=auth(teacher_token))
    assert graded.status_code == 200
    assert graded.json()['status'] == 'graded'
    assert graded.json()['grade'] == 18
    student_view = client.get('/api/v1/submissions', headers=auth(student_token)).json()
    assert student_view[0]['feedback'] == 'Clear reasoning.'
    assert client.get(f'/api/v1/submissions/{submission_id}/file', headers=auth(student_token)).status_code == 200
    other_login = client.post('/api/v1/auth/login', json={'email': 'other@example.com', 'password': 'other-pass'})
    assert client.get(f'/api/v1/submissions/{submission_id}/file', headers=auth(other_login.json()['access_token'])).status_code == 404
    updated_rubric = client.post(f"/api/v1/assignments/{assignment['id']}/rubric", json={'title': 'Revised reflection rubric', 'criteria': [{'name': 'Evidence', 'maximum_score': 20}]}, headers=auth(teacher_token))
    assert updated_rubric.status_code == 201
    assert updated_rubric.json()['id'] == rubric.json()['id']
    assert updated_rubric.json()['criteria'][0]['name'] == 'Evidence'


def test_submission_checks_byte_limit_and_signature(client, teacher_token, student_token):
    assignment = client.post('/api/v1/assignments', json={'title': 'Validated upload', 'subject': 'Foundations', 'section': 'A', 'status': 'active', 'max_marks': 20, 'allowed_file_types': ['.txt', '.pdf'], 'max_file_size': 4}, headers=auth(teacher_token)).json()
    oversize = client.post('/api/v1/submissions', data={'assignment_id': assignment['id']}, files={'file': ('work.txt', b'12345')}, headers=auth(student_token))
    assert oversize.status_code == 400
    wrong_signature = client.post('/api/v1/submissions', data={'assignment_id': assignment['id']}, files={'file': ('work.pdf', b'this is not pdf')}, headers=auth(student_token))
    assert wrong_signature.status_code == 400


def test_teacher_reporting_monitoring_and_warning_signals(client, teacher_token, student_token, monkeypatch):
    monkeypatch.setattr('backend.app.main.predict_risk', lambda _: {
        'risk_level': 'HIGH',
        'risk_probability': 0.8,
        'risk_probability_semantics': 'P(risk_level)',
        'risk_level_policy': 'argmax(class_probabilities)',
        'class_probabilities': {'HIGH': 0.8, 'LOW': 0.1, 'MEDIUM': 0.1},
        'model_version': 'risk-test',
    })
    teacher = auth(teacher_token)
    student = auth(student_token)
    monitoring = client.get('/api/v1/risk/monitoring', headers=teacher)
    assert monitoring.status_code == 200
    assert monitoring.json()['momentum']['INSUFFICIENT_DATA'] == 2
    warnings = client.get('/api/v1/early-warnings', headers=teacher)
    assert warnings.status_code == 200
    assert warnings.json()[0]['detected_at']
    assert 'department' in warnings.json()[0] and 'course' in warnings.json()[0]
    for report_type in ('risk', 'class', 'assignments', 'interventions'):
        response = client.get(f'/api/v1/reports/export.csv?report_type={report_type}', headers=teacher)
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/csv')
        if report_type == 'risk':
            assert 'risk_class_probability' in response.text.splitlines()[0]
    assert client.get('/api/v1/reports/export.csv', headers=student).status_code == 403