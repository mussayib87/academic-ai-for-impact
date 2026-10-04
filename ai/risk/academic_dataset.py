import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal
from backend.app.models import AcademicDataImportBatch, AcademicDataImportRow, AcademicRiskOutcome, Student, StudentSubjectAcademicRecord, Subject

DATASET_FIELDS = (
    'student_id',
    'subject_code',
    'academic_period',
    'fa1',
    'fa1_observed_at',
    'fa2',
    'fa2_observed_at',
    'assignment_mark',
    'assignment_observed_at',
    'attendance_rate',
    'attendance_observed_at',
    'academic_record_updated_at',
    'risk_target',
    'risk_observed_at',
    'outcome_source',
    'temporally_aligned',
    'academic_import_batch_id',
    'academic_source_filename',
    'risk_outcome_import_batch_id',
    'risk_outcome_source_filename',
)
DATASET_CONTRACT = {
    'version': 'student-subject-period-v1',
    'row_unit': 'one student + one subject + one academic period',
    'target_scope': 'global student-period outcome',
    'outcome_join': 'same student and exact academic period; independent source only',
    'feature_temporal_rule': 'every included value must have a source-observation date no later than the matched outcome, and the recorded revision must predate the outcome',
    'training_policy': 'export only; no automatic aggregation, preprocessing, or training',
}
MIN_COMPLETE_ALIGNED_OBSERVATIONS = 100
MIN_DISTINCT_ACADEMIC_PERIODS = 3
MIN_UNIQUE_STUDENTS_PER_CLASS = 20


def build_observation_rows(db: Session) -> list[dict[str, Any]]:
    outcome_join = and_(
        AcademicRiskOutcome.student_id == StudentSubjectAcademicRecord.student_id,
        AcademicRiskOutcome.academic_period == StudentSubjectAcademicRecord.academic_period,
    )
    query = (
        db.query(Student, Subject, StudentSubjectAcademicRecord, AcademicRiskOutcome)
        .join(Student, Student.id == StudentSubjectAcademicRecord.student_id)
        .join(Subject, Subject.id == StudentSubjectAcademicRecord.subject_id)
        .outerjoin(AcademicRiskOutcome, outcome_join)
        .order_by(Student.student_id, StudentSubjectAcademicRecord.academic_period, Subject.code)
    )
    rows = []
    for student, subject, record, outcome in query.all():
        academic_batch = db.query(AcademicDataImportBatch).filter_by(id=record.import_batch_id).first() if record.import_batch_id else None
        outcome_batch = db.query(AcademicDataImportBatch).filter_by(id=outcome.import_batch_id).first() if outcome and outcome.import_batch_id else None
        outcome_at = outcome.observed_at if outcome else None
        source_values = (
            (record.fa1, record.fa1_observed_at),
            (record.fa2, record.fa2_observed_at),
            (record.assignment_mark, record.assignment_observed_at),
            (record.attendance_rate, record.attendance_observed_at),
        )
        complete_marks = record.fa1 is not None and record.fa2 is not None
        dates_precede_outcome = bool(outcome_at) and all(
            not (value is not None and (observed_at is None or observed_at > outcome_at))
            for value, observed_at in source_values
        )
        temporally_aligned = bool(outcome and complete_marks and dates_precede_outcome)
        rows.append({
            'student_id': student.student_id,
            'subject_code': subject.code,
            'academic_period': record.academic_period,
            'fa1': record.fa1,
            'fa1_observed_at': record.fa1_observed_at.isoformat() if record.fa1_observed_at else None,
            'fa2': record.fa2,
            'fa2_observed_at': record.fa2_observed_at.isoformat() if record.fa2_observed_at else None,
            'assignment_mark': record.assignment_mark,
            'assignment_observed_at': record.assignment_observed_at.isoformat() if record.assignment_observed_at else None,
            'attendance_rate': record.attendance_rate,
            'attendance_observed_at': record.attendance_observed_at.isoformat() if record.attendance_observed_at else None,
            'academic_record_updated_at': record.updated_at.isoformat(),
            'risk_target': outcome.risk_level if temporally_aligned else None,
            'risk_observed_at': outcome.observed_at.isoformat() if temporally_aligned else None,
            'outcome_source': outcome.outcome_source if temporally_aligned else None,
            'temporally_aligned': temporally_aligned,
            'academic_import_batch_id': record.import_batch_id,
            'academic_source_filename': academic_batch.source_filename if academic_batch else None,
            'risk_outcome_import_batch_id': outcome.import_batch_id if outcome else None,
            'risk_outcome_source_filename': outcome_batch.source_filename if outcome_batch else None,
        })
    return rows


def readiness_report(db: Session) -> dict[str, Any]:
    student_count = db.query(Student.id).count()
    records = db.query(StudentSubjectAcademicRecord).all()
    outcomes = db.query(AcademicRiskOutcome).all()
    record_count = len(records)
    fa1_present = sum(record.fa1 is not None for record in records)
    fa2_present = sum(record.fa2 is not None for record in records)
    complete_marks = [record for record in records if record.fa1 is not None and record.fa2 is not None]
    valid_outcomes_by_key = {(item.student_id, item.academic_period): item for item in outcomes if item.risk_level in {'HIGH', 'MEDIUM', 'LOW'} and item.outcome_source.strip()}
    complete_aligned = []
    for record in complete_marks:
        outcome = valid_outcomes_by_key.get((record.student_id, record.academic_period))
        if outcome is None:
            continue
        timed_values = (
            (record.fa1, record.fa1_observed_at),
            (record.fa2, record.fa2_observed_at),
            (record.assignment_mark, record.assignment_observed_at),
            (record.attendance_rate, record.attendance_observed_at),
        )
        if any(value is not None and (observed_at is None or observed_at > outcome.observed_at) for value, observed_at in timed_values):
            continue
        complete_aligned.append(record)
    target_students = {
        level: {
            record.student_id
            for record in complete_aligned
            if valid_outcomes_by_key[(record.student_id, record.academic_period)].risk_level == level
        }
        for level in ('HIGH', 'MEDIUM', 'LOW')
    }
    distinct_periods = sorted({record.academic_period for record in records if record.academic_period != 'UNSPECIFIED'})
    duplicate_record_groups = db.query(
        StudentSubjectAcademicRecord.student_id,
        StudentSubjectAcademicRecord.subject_id,
        StudentSubjectAcademicRecord.academic_period,
        func.count(StudentSubjectAcademicRecord.id),
    ).group_by(
        StudentSubjectAcademicRecord.student_id,
        StudentSubjectAcademicRecord.subject_id,
        StudentSubjectAcademicRecord.academic_period,
    ).having(func.count(StudentSubjectAcademicRecord.id) > 1).all()
    duplicate_outcome_groups = db.query(
        AcademicRiskOutcome.student_id,
        AcademicRiskOutcome.academic_period,
        func.count(AcademicRiskOutcome.id),
    ).group_by(AcademicRiskOutcome.student_id, AcademicRiskOutcome.academic_period).having(func.count(AcademicRiskOutcome.id) > 1).all()
    academic_batches = db.query(AcademicDataImportBatch).filter(AcademicDataImportBatch.dataset_type == 'subject_records').all()
    duplicate_import_rows = sum(batch.duplicate_rows for batch in academic_batches)
    rejected_import_rows = db.query(AcademicDataImportRow).filter_by(dataset_type='subject_records', status='rejected').all()
    conflicting_import_rows = sum(
        any('conflicting duplicate' in error.casefold() for error in (row.errors or []))
        for row in rejected_import_rows
    )
    invalid_fa1 = sum(record.fa1 is not None and not 0 <= record.fa1 <= 25 for record in records)
    invalid_fa2 = sum(record.fa2 is not None and not 0 <= record.fa2 <= 25 for record in records)
    invalid_assignment = sum(record.assignment_mark is not None and not 0 <= record.assignment_mark <= 25 for record in records)
    invalid_attendance = sum(record.attendance_rate is not None and not 0 <= record.attendance_rate <= 100 for record in records)
    missing_fa1 = record_count - fa1_present
    missing_fa2 = record_count - fa2_present
    complete_aligned_count = len(complete_aligned)
    coverage_threshold_met = (
        complete_aligned_count >= MIN_COMPLETE_ALIGNED_OBSERVATIONS
        and len(distinct_periods) >= MIN_DISTINCT_ACADEMIC_PERIODS
        and all(len(target_students[level]) >= MIN_UNIQUE_STUDENTS_PER_CLASS for level in ('HIGH', 'MEDIUM', 'LOW'))
        and not (invalid_fa1 or invalid_fa2 or invalid_assignment or invalid_attendance)
        and not duplicate_record_groups
        and not duplicate_outcome_groups
    )
    blockers = []
    if complete_aligned_count < MIN_COMPLETE_ALIGNED_OBSERVATIONS:
        blockers.append(f'Need at least {MIN_COMPLETE_ALIGNED_OBSERVATIONS} complete, period-matched observations with outcomes.')
    if len(distinct_periods) < MIN_DISTINCT_ACADEMIC_PERIODS:
        blockers.append(f'Need at least {MIN_DISTINCT_ACADEMIC_PERIODS} distinct academic periods for out-of-time validation.')
    for level in ('HIGH', 'MEDIUM', 'LOW'):
        if len(target_students[level]) < MIN_UNIQUE_STUDENTS_PER_CLASS:
            blockers.append(f'Need at least {MIN_UNIQUE_STUDENTS_PER_CLASS} distinct students with complete aligned {level} outcomes.')
    if invalid_fa1 or invalid_fa2 or invalid_assignment or invalid_attendance:
        blockers.append('Invalid academic values must be corrected.')
    if duplicate_record_groups or duplicate_outcome_groups:
        blockers.append('Duplicate student/subject/period records or student/period outcomes must be resolved.')
    blockers.append('A validated aggregation strategy from subject-period observations to the existing global student-period target is not yet approved.')
    return {
        'data_contract': DATASET_CONTRACT,
        'training_ready': False,
        'data_coverage_gate_met': coverage_threshold_met,
        'students_in_database': student_count,
        'students_with_subject_records': len({record.student_id for record in records}),
        'subject_records': record_count,
        'fa1_present': fa1_present,
        'fa1_missing': missing_fa1,
        'fa1_missing_percent': (missing_fa1 / record_count * 100) if record_count else None,
        'fa2_present': fa2_present,
        'fa2_missing': missing_fa2,
        'fa2_missing_percent': (missing_fa2 / record_count * 100) if record_count else None,
        'complete_fa1_fa2_observations': len(complete_marks),
        'risk_outcomes': len(outcomes),
        'complete_period_aligned_observations_with_valid_target': complete_aligned_count,
        'distinct_academic_periods': distinct_periods,
        'unique_students_per_target': {level: len(target_students[level]) for level in target_students},
        'duplicate_record_groups': len(duplicate_record_groups),
        'duplicate_outcome_groups': len(duplicate_outcome_groups),
        'duplicate_import_rows': duplicate_import_rows,
        'conflicting_import_rows_rejected': conflicting_import_rows,
        'other_rejected_import_rows': len(rejected_import_rows) - conflicting_import_rows,
        'invalid_values': {'fa1': invalid_fa1, 'fa2': invalid_fa2, 'assignment_mark': invalid_assignment, 'attendance_rate': invalid_attendance},
        'aggregation_strategy': None,
        'blockers': blockers,
        'readiness_thresholds': {
            'minimum_complete_aligned_observations': MIN_COMPLETE_ALIGNED_OBSERVATIONS,
            'minimum_distinct_academic_periods': MIN_DISTINCT_ACADEMIC_PERIODS,
            'minimum_unique_students_per_class': MIN_UNIQUE_STUDENTS_PER_CLASS,
        },
    }


def export_observations(db: Session, output_path: Path) -> dict[str, Any]:
    rows = build_observation_rows(db)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=DATASET_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return {'rows': len(rows), 'path': str(output_path), 'readiness': readiness_report(db)}


def main() -> None:
    parser = argparse.ArgumentParser(description='Export real subject-period academic observations for future ML review; never trains a model.')
    parser.add_argument('--output', type=Path, default=Path('data/processed/subject_academic_observations.csv'))
    args = parser.parse_args()
    with SessionLocal() as db:
        print(json.dumps(export_observations(db, args.output), indent=2))


if __name__ == '__main__':
    main()
