import csv
import io

import pytest

from backend.app.database import get_db
from backend.app.main import app
from backend.app.models import AcademicDataImportBatch, Assignment, AuditLog, Student, StudentSubjectAcademicRecord, Submission, Subject

PERIOD = '2026-S1'


def auth(token):
    return {'Authorization': f'Bearer {token}'}


def ensure_subjects(client):
    override = app.dependency_overrides[get_db]
    with next(override()) as db:
        values = {
            'EVS': 'Environmental Studies',
            'CN': 'Computer Networks',
            'TOC': 'Theory of Computation',
            'RM': 'Research Methodology',
            'SE': 'Software Engineering',
        }
        for code, name in values.items():
            if db.query(Subject).filter_by(code=code).first() is None:
                db.add(Subject(code=code, name=name, department='Engineering'))
        db.commit()


def test_register_formula_subject_isolation_boundaries_and_access(client, teacher_token, student_token):
    ensure_subjects(client)
    teacher = auth(teacher_token)
    student = auth(student_token)
    register = client.get(f'/api/v1/academic-register?limit=500&academic_period={PERIOD}', headers=teacher)
    assert register.status_code == 200
    assert register.json()['total'] == 2
    assert {item['code'] for item in register.json()['subjects']} == {'EVS', 'CN', 'TOC', 'RM', 'SE'}
    student_id = client.app.state.test_student_id

    changed = None
    for code in ('EVS', 'CN', 'TOC', 'RM', 'SE'):
        changed = client.patch(
            f'/api/v1/academic-register/{student_id}/{code}?academic_period={PERIOD}',
            json={'fa1': 21, 'fa2': 18, 'assignment_mark': 22, 'attendance_rate': 87},
            headers=teacher,
        )
        assert changed.status_code == 200
        assert changed.json()['internal_mark'] == pytest.approx(41.5)
        assert changed.json()['fa_average'] == pytest.approx(19.5)

    row = changed.json()['register_row']
    assert row['total_internal'] == pytest.approx(207.5)
    assert row['average_internal'] == pytest.approx(41.5)
    before = client.get(f'/api/v1/students/{student_id}/academic-records?academic_period={PERIOD}', headers=teacher).json()
    updated = client.patch(f'/api/v1/academic-register/{student_id}/CN?academic_period={PERIOD}', json={'fa1': 0, 'fa2': 0, 'assignment_mark': 0}, headers=teacher)
    assert updated.json()['internal_mark'] == 0
    after = client.get(f'/api/v1/students/{student_id}/academic-records?academic_period={PERIOD}', headers=teacher).json()
    assert after['subjects']['CN']['internal_mark'] == 0
    assert after['subjects']['EVS']['internal_mark'] == pytest.approx(41.5)
    assert before['subjects']['TOC'] == after['subjects']['TOC']

    maximum = client.patch(f'/api/v1/academic-register/{student_id}/CN?academic_period={PERIOD}', json={'fa1': 25, 'fa2': 25, 'assignment_mark': 25}, headers=teacher)
    assert maximum.status_code == 200
    assert maximum.json()['internal_mark'] == 50
    assert client.patch(f'/api/v1/academic-register/{student_id}/CN?academic_period={PERIOD}', json={'attendance_rate': 0}, headers=teacher).json()['attendance_rate'] == 0
    assert client.patch(f'/api/v1/academic-register/{student_id}/CN?academic_period={PERIOD}', json={'attendance_rate': 100}, headers=teacher).json()['attendance_rate'] == 100
    for field, value in (('fa1', -1), ('fa2', 26), ('assignment_mark', 100), ('attendance_rate', 101), ('attendance_rate', -1)):
        response = client.patch(f'/api/v1/academic-register/{student_id}/CN?academic_period={PERIOD}', json={field: value}, headers=teacher)
        assert response.status_code == 422

    assert client.get('/api/v1/academic-register', headers=student).status_code == 403
    assert client.patch(f'/api/v1/academic-register/{student_id}/CN?academic_period={PERIOD}', json={'fa1': 1}, headers=student).status_code == 403
    own = client.get('/api/v1/students/me/academic-records', headers=student)
    assert own.status_code == 200
    assert own.json()['student_id'] == 'T-001'
    assert client.get(f'/api/v1/students/{client.app.state.test_other_student_id}/academic-records', headers=student).status_code == 403


def test_subject_marks_do_not_change_global_model_prediction(client, teacher_token):
    ensure_subjects(client)
    headers = auth(teacher_token)
    student_id = client.app.state.test_student_id
    before = client.get(f'/api/v1/students/{student_id}', headers=headers).json()['student']
    updated = client.patch(f'/api/v1/academic-register/{student_id}/CN?academic_period={PERIOD}', json={
        'fa1': 0, 'fa2': 25, 'assignment_mark': 25, 'attendance_rate': 100,
    }, headers=headers)
    assert updated.status_code == 200
    after = client.get(f'/api/v1/students/{student_id}', headers=headers).json()['student']
    assert after['risk_level'] == before['risk_level']
    assert after['risk_probability'] == before['risk_probability']
    assert after['class_probabilities'] == before['class_probabilities']
    assert after['risk_level'] == max(after['class_probabilities'], key=after['class_probabilities'].get)


def test_subject_import_tracks_provenance_and_exports_calculated_register(client, teacher_token):
    ensure_subjects(client)
    student_id = client.app.state.test_student_id
    response = client.post(
        '/api/v1/academic-data/import',
        data={'dataset_type': 'subject_records'},
        files={'file': ('cn-marks.csv', b'student_id,subject_code,academic_period,fa1,fa2,assignment_mark,attendance_rate\nT-001,CN,2026-S1,21,18,22,87\n', 'text/csv')},
        headers=auth(teacher_token),
    )
    assert response.status_code == 200
    result = response.json()
    assert result['imported_rows'] == 1
    override = app.dependency_overrides[get_db]
    with next(override()) as db:
        record = db.query(StudentSubjectAcademicRecord).filter_by(student_id=student_id).one()
        assert record.subject.code == 'CN'
        assert record.import_batch_id == result['batch_id']
        assert db.query(AcademicDataImportBatch).filter_by(id=result['batch_id']).one().imported_by_user_id
        audit = db.query(AuditLog).filter_by(action='academic_subject_record.imported').one()
        assert audit.detail['subject_code'] == 'CN'

    records = client.get(f'/api/v1/students/{student_id}/academic-records?academic_period={PERIOD}', headers=auth(teacher_token)).json()
    assert records['subjects']['CN']['internal_mark'] == pytest.approx(41.5)
    assert records['subjects']['EVS']['fa1'] is None
    exported = client.get('/api/v1/reports/export.csv?report_type=internal_marks', headers=auth(teacher_token))
    assert exported.status_code == 200
    parsed = list(csv.reader(io.StringIO(exported.text)))
    assert 'CN FA1 /25' in parsed[0]
    assert 'Total Internal /250' in parsed[0]
    assert parsed[1][0] == PERIOD
    assert parsed[1][1] == 'T-001'
    assert parsed[1][parsed[0].index('CN Internal /50')] == '41.5'


def test_subject_import_rejects_unknown_subject_and_teacher_assignment_is_subject_linked(client, teacher_token, student_token):
    ensure_subjects(client)
    rejected = client.post(
        '/api/v1/academic-data/import',
        data={'dataset_type': 'subject_records'},
        files={'file': ('unknown.csv', b'student_id,subject_code,academic_period,fa1\nT-001,UNKNOWN,2026-S1,10\n', 'text/csv')},
        headers=auth(teacher_token),
    )
    assert rejected.status_code == 200
    assert rejected.json()['rejected_rows'] == 1
    assert 'Unknown subject_code' in rejected.json()['validation_errors'][0]['errors'][0]

    assignment = client.post('/api/v1/assignments', json={
        'title': 'CN handwritten pages', 'subject': 'Computer Networks', 'section': 'A',
        'status': 'active', 'max_marks': 25, 'allowed_file_types': ['.png', '.jpg', '.jpeg'],
    }, headers=auth(teacher_token))
    assert assignment.status_code == 201
    assert assignment.json()['subject'] == 'Computer Networks'
    assert assignment.json()['subject_id'] is not None
    cn_assignments = client.get('/api/v1/assignments?subject_code=CN', headers=auth(student_token))
    evs_assignments = client.get('/api/v1/assignments?subject_code=EVS', headers=auth(student_token))
    assert [item['id'] for item in cn_assignments.json()] == [assignment.json()['id']]
    assert evs_assignments.json() == []
    assert client.post('/api/v1/assignments', json={
        'title': 'Too many marks', 'subject': 'CN', 'max_marks': 26,
    }, headers=auth(teacher_token)).status_code == 422


def test_assignment_roster_tracks_missing_students_and_multiple_image_pages(client, teacher_token, student_token):
    ensure_subjects(client)
    teacher = auth(teacher_token)
    student = auth(student_token)
    created = client.post('/api/v1/assignments', json={
        'title': 'CN handwritten pages', 'subject': 'CN', 'section': None, 'status': 'active',
        'max_marks': 25, 'allowed_file_types': ['.png'],
    }, headers=teacher)
    assert created.status_code == 201
    assignment_id = created.json()['id']
    initial = client.get(f'/api/v1/assignments/{assignment_id}/summary', headers=teacher).json()
    assert initial['counts']['assigned'] == 2
    assert initial['counts']['not_submitted'] == 2
    assert all(item['uploaded'] is False and item['status'] == 'not_submitted' for item in initial['students'])

    files = [
        ('files', ('page-1.png', b'\x89PNG\r\n\x1a\npage-one', 'image/png')),
        ('files', ('page-2.png', b'\x89PNG\r\n\x1a\npage-two', 'image/png')),
    ]
    submitted = client.post('/api/v1/submissions', data={'assignment_id': assignment_id}, files=files, headers=student)
    assert submitted.status_code == 201
    assert submitted.json()['page_count'] == 2
    submission_id = submitted.json()['id']
    versions_response = client.get(f'/api/v1/submissions/{submission_id}/versions', headers=teacher)
    assert versions_response.status_code == 200
    versions = versions_response.json()
    assert [(item['page_number'], item['page_count']) for item in versions] == [(2, 2), (1, 2)]
    preview = client.get(f"/api/v1/submissions/{submission_id}/versions/{versions[-1]['id']}/file", headers=teacher)
    assert preview.status_code == 200
    assert preview.content.startswith(b'\x89PNG\r\n\x1a\n')
    other = client.post('/api/v1/auth/login', json={'email': 'other@example.com', 'password': 'other-pass'}).json()['access_token']
    assert client.get(f"/api/v1/submissions/{submission_id}/versions/{versions[-1]['id']}/file", headers=auth(other)).status_code == 404

    final = client.get(f'/api/v1/assignments/{assignment_id}/summary', headers=teacher).json()
    first_student = next(item for item in final['students'] if item['student_id'] == 'T-001')
    missing_student = next(item for item in final['students'] if item['student_id'] == 'T-002')
    assert final['counts']['submitted'] == 1
    assert final['counts']['not_submitted'] == 1
    assert first_student['uploaded'] is True and first_student['pages'] == 2
    assert missing_student['uploaded'] is False and missing_student['status'] == 'not_submitted'


def test_assignment_image_mime_mismatch_is_rejected(client, teacher_token, student_token):
    ensure_subjects(client)
    assignment = client.post('/api/v1/assignments', json={
        'title': 'CN image upload', 'subject': 'CN', 'section': 'A', 'status': 'active',
        'max_marks': 25, 'allowed_file_types': ['.png'],
    }, headers=auth(teacher_token)).json()
    response = client.post('/api/v1/submissions', data={'assignment_id': assignment['id']}, files={
        'file': ('page.png', b'\x89PNG\r\n\x1a\ncontent', 'image/jpeg'),
    }, headers=auth(student_token))
    assert response.status_code == 400
    assert 'MIME type' in response.json()['detail']


def test_legacy_assignment_grade_ceiling_is_preserved(client, teacher_token):
    override = app.dependency_overrides[get_db]
    with next(override()) as db:
        student = db.query(Student).filter_by(student_id='T-001').one()
        assignment = Assignment(title='Legacy coursework', subject='Academic Foundations', max_marks=100, status='active')
        db.add(assignment)
        db.flush()
        submission = Submission(student_id=student.id, assignment_id=assignment.id, status='submitted', stored_path='legacy-file')
        db.add(submission)
        db.commit()
        submission_id = submission.id
    response = client.patch(f'/api/v1/submissions/{submission_id}/grade', json={'grade': 40, 'feedback': 'Reviewed'}, headers=auth(teacher_token))
    assert response.status_code == 200
    assert response.json()['grade'] == 40
