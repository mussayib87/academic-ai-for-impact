import csv
import io
from openpyxl import Workbook

from ai.risk.academic_dataset import build_observation_rows, readiness_report
from backend.app.database import get_db
from backend.app.main import app
from backend.app.models import AcademicRiskOutcome, StudentSubjectAcademicRecord, StudentSubjectAcademicRecordHistory, Subject


def auth(token):
    return {'Authorization': f'Bearer {token}'}


def ensure_subjects():
    override = app.dependency_overrides[get_db]
    with next(override()) as db:
        if db.query(Subject).filter_by(code='CN').first() is None:
            db.add(Subject(code='CN', name='Computer Networks', department='Engineering'))
            db.commit()


def upload(client, token, kind, filename, content):
    return client.post(
        '/api/v1/academic-data/import',
        data={'dataset_type': kind},
        files={'file': (filename, content.encode('utf-8'), 'text/csv')},
        headers=auth(token),
    )


def test_period_scoped_imports_corrections_and_history(client, teacher_token):
    ensure_subjects()
    student_id = client.app.state.test_student_id
    first = upload(
        client, teacher_token, 'subject_records', 'cn-s1.csv',
        'USN,Subject,Academic_Period,FA1,FA1_Observed_At\nT-001,CN,2026-S1,20,2026-04-20\n',
    )
    second = upload(
        client, teacher_token, 'subject_records', 'cn-s2.csv',
        'USN,Subject,Academic_Period,FA1,FA1_Observed_At\nT-001,CN,2026-S2,15,2026-09-20\n',
    )
    assert first.status_code == second.status_code == 200
    fa2_only = upload(
        client, teacher_token, 'subject_records', 'cn-s2-fa2.csv',
        'student_id,subject_code,academic_period,fa2,fa2_observed_at\nT-001,CN,2026-S2,17,2026-09-21\n',
    )
    assert fa2_only.status_code == 200
    repeated = upload(
        client, teacher_token, 'subject_records', 'repeat.csv',
        'USN,Subject,Academic_Period,FA1,FA1_Observed_At\nT-001,CN,2026-S1,20,2026-04-20\n',
    )
    assert repeated.json()['duplicate_import'] is True
    override = app.dependency_overrides[get_db]
    with next(override()) as db:
        records = db.query(StudentSubjectAcademicRecord).filter_by(student_id=student_id).order_by(StudentSubjectAcademicRecord.academic_period).all()
        assert [(item.academic_period, item.fa1, item.fa2) for item in records] == [('2026-S1', 20, None), ('2026-S2', 15, 17)]

    correction = upload(
        client, teacher_token, 'subject_records', 'cn-s1-correction.csv',
        'student_id,subject_code,academic_period,fa1,fa1_observed_at\nT-001,CN,2026-S1,21,2026-04-21\n',
    )
    assert correction.status_code == 200
    s1 = client.get('/api/v1/students/1/academic-records?academic_period=2026-S1', headers=auth(teacher_token)).json()
    s2 = client.get('/api/v1/students/1/academic-records?academic_period=2026-S2', headers=auth(teacher_token)).json()
    assert s1['subjects']['CN']['fa1'] == 21
    assert s2['subjects']['CN']['fa1'] == 15
    assert s2['subjects']['CN']['fa2'] == 17
    with next(override()) as db:
        assert db.query(StudentSubjectAcademicRecord).filter_by(student_id=student_id).count() == 2
        history = db.query(StudentSubjectAcademicRecordHistory).filter_by(academic_record_id=s1['subjects']['CN']['record_id']).all()
        assert len(history) == 2
        assert db.query(AcademicRiskOutcome).count() == 0


def test_outcome_alignment_export_and_readiness_do_not_promote_marks_to_training(client, teacher_token):
    ensure_subjects()
    marks = upload(
        client, teacher_token, 'subject_records', 'aligned.csv',
        'student_id,subject_code,academic_period,fa1,fa1_observed_at,fa2,fa2_observed_at,assignment_mark,assignment_observed_at,attendance_rate,attendance_observed_at\n'
        'T-001,CN,2026-S1,20,2026-09-01,18,2026-09-02,22,2026-09-03,87,2026-09-01\n',
    )
    outcome = upload(
        client, teacher_token, 'risk_outcomes', 'independent-outcome.csv',
        'student_id,academic_period,risk_target,observed_at,outcome_source\nT-001,2026-S1,MEDIUM,2026-10-02,independent faculty review\n',
    )
    assert marks.status_code == outcome.status_code == 200
    override = app.dependency_overrides[get_db]
    with next(override()) as db:
        rows = build_observation_rows(db)
        row = next(item for item in rows if item['student_id'] == 'T-001' and item['subject_code'] == 'CN')
        report = readiness_report(db)
    assert row['fa1'] == 20 and row['fa2'] == 18
    assert row['academic_period'] == '2026-S1'
    assert row['risk_target'] == 'MEDIUM'
    assert row['temporally_aligned'] is True
    assert row['academic_import_batch_id'] == marks.json()['batch_id']
    assert row['risk_outcome_import_batch_id'] == outcome.json()['batch_id']
    assert report['complete_period_aligned_observations_with_valid_target'] == 1
    assert report['training_ready'] is False
    assert any('aggregation strategy' in reason for reason in report['blockers'])

    export = client.get('/api/v1/ml/academic-data/export.csv', headers=auth(teacher_token))
    assert export.status_code == 200
    exported = next(csv.DictReader(io.StringIO(export.text)))
    assert exported['risk_target'] == 'MEDIUM'
    assert exported['fa1'] == '20.0'
    assert exported['temporally_aligned'] == 'True'
    assert client.get('/api/v1/ml/academic-data/readiness', headers=auth(teacher_token)).json()['training_ready'] is False


def test_future_mark_is_not_joined_as_a_past_prediction_feature(client, teacher_token):
    ensure_subjects()
    upload(
        client, teacher_token, 'subject_records', 'future-fa2.csv',
        'student_id,subject_code,academic_period,fa1,fa1_observed_at,fa2,fa2_observed_at\nT-001,CN,2026-S1,20,2026-09-01,18,2026-10-03\n',
    )
    upload(
        client, teacher_token, 'risk_outcomes', 'earlier-outcome.csv',
        'student_id,academic_period,risk_target,observed_at,outcome_source\nT-001,2026-S1,MEDIUM,2026-10-02,independent review\n',
    )
    override = app.dependency_overrides[get_db]
    with next(override()) as db:
        row = next(item for item in build_observation_rows(db) if item['student_id'] == 'T-001')
    assert row['temporally_aligned'] is False
    assert row['risk_target'] is None
    assert row['risk_observed_at'] is None


def test_conflicting_duplicate_subject_rows_are_rejected(client, teacher_token):
    ensure_subjects()
    response = upload(
        client, teacher_token, 'subject_records', 'conflict.csv',
        'student_id,subject_code,academic_period,fa1\nT-001,CN,2026-S1,20\nT-001,CN,2026-S1,21\n',
    )
    assert response.status_code == 200
    assert response.json()['imported_rows'] == 0
    assert response.json()['rejected_rows'] == 2
    assert all('Conflicting duplicate' in error for row in response.json()['validation_errors'] for error in row['errors'])
    override = app.dependency_overrides[get_db]
    with next(override()) as db:
        report = readiness_report(db)
    assert report['conflicting_import_rows_rejected'] == 2


def test_invalid_and_unknown_subject_mark_rows_report_identity_and_field(client, teacher_token):
    ensure_subjects()
    response = upload(
        client, teacher_token, 'subject_records', 'invalid.csv',
        'USN,Subject,Academic_Period,FA1,FA2\n'
        'T-001,CN,2026-S1,26,18\n'
        'T-001,CN,2026-S1,20,-1\n'
        'UNKNOWN,CN,2026-S1,20,18\n'
        'T-001,UNKNOWN,2026-S1,20,18\n',
    )
    assert response.status_code == 200
    errors = response.json()['validation_errors']
    assert response.json()['imported_rows'] == 0
    assert response.json()['rejected_rows'] == 4
    assert [(item['student_id'], item['subject_code']) for item in errors] == [
        ('T-001', 'CN'), ('T-001', 'CN'), ('UNKNOWN', 'CN'), ('T-001', 'UNKNOWN'),
    ]
    assert 'fa1 must be between 0 and 25' in errors[0]['errors'][0]
    assert 'fa2 must be between 0 and 25' in errors[1]['errors'][0]
    assert 'Unknown student_id' in errors[2]['errors'][0]
    assert 'Unknown subject_code' in errors[3]['errors'][0]


def test_marks_without_observation_dates_are_not_ml_aligned(client, teacher_token):
    ensure_subjects()
    upload(
        client, teacher_token, 'subject_records', 'no-dates.csv',
        'student_id,subject_code,academic_period,fa1,fa2\nT-001,CN,2026-S1,20,18\n',
    )
    upload(
        client, teacher_token, 'risk_outcomes', 'outcome.csv',
        'student_id,academic_period,risk_target,observed_at,outcome_source\nT-001,2026-S1,MEDIUM,2026-10-02,independent review\n',
    )
    override = app.dependency_overrides[get_db]
    with next(override()) as db:
        row = next(item for item in build_observation_rows(db) if item['student_id'] == 'T-001')
        report = readiness_report(db)
    assert row['fa1'] == 20 and row['fa2'] == 18
    assert row['risk_target'] is None
    assert row['temporally_aligned'] is False
    assert report['complete_fa1_fa2_observations'] == 1
    assert report['complete_period_aligned_observations_with_valid_target'] == 0


def test_combined_subject_marks_xlsx_import_preserves_period_and_source_dates(client, teacher_token):
    override = app.dependency_overrides[get_db]
    with next(override()) as db:
        db.add(Subject(code='EVS', name='Environmental Studies', department='Sciences'))
        db.commit()
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(['USN', 'Subject', 'Academic_Period', 'FA1', 'FA1_Observed_At', 'FA2', 'FA2_Observed_At'])
    sheet.append(['T-001', 'EVS', '2026-S1', 20, '2026-04-20', 18, '2026-05-20'])
    content = io.BytesIO()
    workbook.save(content)
    response = client.post(
        '/api/v1/academic-data/import',
        data={'dataset_type': 'subject_records'},
        files={'file': ('evs-fa.xlsx', content.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
        headers=auth(teacher_token),
    )
    assert response.status_code == 200
    record = client.get('/api/v1/students/1/academic-records?academic_period=2026-S1', headers=auth(teacher_token)).json()['subjects']['EVS']
    assert record['fa1'] == 20
    assert record['fa2'] == 18
    assert record['fa1_observed_at'].startswith('2026-04-20')
    assert record['fa2_observed_at'].startswith('2026-05-20')
