import re
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models import AcademicRiskOutcome, Student, StudentSubjectAcademicRecord, Subject

SUBJECTS = {
    'EVS': 'Environmental Studies',
    'CN': 'Computer Networks',
    'TOC': 'Theory of Computation',
    'RM': 'Research Methodology',
    'SE': 'Software Engineering',
}
MARK_FIELDS = ('fa1', 'fa2', 'assignment_mark')
ACADEMIC_PERIOD_PATTERN = re.compile(r'^\d{4}-S[12]$')


def normalize_academic_period(value: str) -> str:
    normalized = value.strip().upper()
    if not ACADEMIC_PERIOD_PATTERN.fullmatch(normalized):
        raise ValueError('academic_period must use the YYYY-S1 or YYYY-S2 format.')
    return normalized


def internal_mark(record: StudentSubjectAcademicRecord | None) -> float | None:
    if record is None or any(getattr(record, field) is None for field in MARK_FIELDS):
        return None
    return (record.fa1 + record.fa2) / 2 + record.assignment_mark


def academic_totals(records: dict[str, StudentSubjectAcademicRecord]) -> dict[str, float | None]:
    internal_marks = {code: internal_mark(records.get(code)) for code in SUBJECTS}
    if any(value is None for value in internal_marks.values()):
        return {'total_internal': None, 'average_internal': None}
    total = sum(value for value in internal_marks.values() if value is not None)
    return {'total_internal': total, 'average_internal': total / len(SUBJECTS)}


def serialize_record(record: StudentSubjectAcademicRecord | None) -> dict[str, Any]:
    return {
        'record_id': record.id if record else None,
        'fa1': record.fa1 if record else None,
        'fa1_observed_at': record.fa1_observed_at.isoformat() if record and record.fa1_observed_at else None,
        'fa2': record.fa2 if record else None,
        'fa2_observed_at': record.fa2_observed_at.isoformat() if record and record.fa2_observed_at else None,
        'assignment_mark': record.assignment_mark if record else None,
        'assignment_observed_at': record.assignment_observed_at.isoformat() if record and record.assignment_observed_at else None,
        'fa_average': (record.fa1 + record.fa2) / 2 if record and record.fa1 is not None and record.fa2 is not None else None,
        'internal_mark': internal_mark(record),
        'attendance_rate': record.attendance_rate if record else None,
        'attendance_observed_at': record.attendance_observed_at.isoformat() if record and record.attendance_observed_at else None,
        'import_batch_id': record.import_batch_id if record else None,
    }


def academic_periods(db: Session) -> list[str]:
    record_periods = db.query(StudentSubjectAcademicRecord.academic_period).distinct().all()
    outcome_periods = db.query(AcademicRiskOutcome.academic_period).distinct().all()
    return sorted({row[0] for row in (*record_periods, *outcome_periods) if row[0] != 'UNSPECIFIED'}, reverse=True)


def selected_academic_period(db: Session, academic_period: str | None) -> str | None:
    if academic_period:
        return normalize_academic_period(academic_period)
    periods = academic_periods(db)
    return periods[0] if periods else None


def subject_records_by_student(db: Session, student_ids: list[int], academic_period: str | None = None) -> dict[int, dict[str, StudentSubjectAcademicRecord]]:
    if not student_ids:
        return {}
    result: dict[int, dict[str, StudentSubjectAcademicRecord]] = {}
    query = (
        db.query(StudentSubjectAcademicRecord)
        .join(Subject)
        .filter(StudentSubjectAcademicRecord.student_id.in_(student_ids), Subject.code.in_(SUBJECTS))
    )
    if academic_period:
        query = query.filter(StudentSubjectAcademicRecord.academic_period == academic_period)
    rows = query.all()
    for record in rows:
        result.setdefault(record.student_id, {})[record.subject.code] = record
    return result


def build_register_row(student: Student, records: dict[str, StudentSubjectAcademicRecord], academic_period: str | None) -> dict[str, Any]:
    subjects = {code: serialize_record(records.get(code)) for code in SUBJECTS}
    return {
        'id': student.id,
        'student_id': student.student_id,
        'full_name': student.full_name,
        'department': student.department,
        'section': student.section,
        'academic_period': academic_period,
        'subjects': subjects,
        **academic_totals(records),
    }
