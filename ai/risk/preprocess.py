import argparse
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from ai.risk.features import FEATURES, TARGET
from backend.app.config import BASE_DIR
from backend.app.database import SessionLocal
from backend.app.models import AcademicMomentum, AssignmentStudent, Student, Submission
from backend.app.services.momentum import calculate_momentum

DEFAULT_OUTPUT = BASE_DIR / 'data' / 'processed' / 'DSstudents_processed.csv'


def build_rows(db: Session) -> list[dict[str, object]]:
    rows = []
    for student in db.query(Student).order_by(Student.id).all():
        observations = db.query(AcademicMomentum).filter(AcademicMomentum.student_id == student.id).order_by(AcademicMomentum.observed_at, AcademicMomentum.id).all()
        by_metric: dict[str, list[float]] = {}
        for observation in observations:
            by_metric.setdefault(observation.metric, []).append(observation.value)
        attendance_trend = calculate_momentum(by_metric.get('attendance', []))
        assessment_trend = calculate_momentum(by_metric.get('assessment', []))
        imported_attendance = [item.value for item in observations if item.metric == 'attendance' and item.import_batch_id is not None]
        imported_assessment = [item.value for item in observations if item.metric == 'assessment' and item.import_batch_id is not None]
        activity_rows = [item.value for item in observations if item.metric == 'activity'][-4:]
        activity_per_week = sum(activity_rows) / max(1, len(activity_rows))
        assigned = db.query(AssignmentStudent.id).filter(AssignmentStudent.student_id == student.id).count()
        submitted = db.query(Submission.id).filter(Submission.student_id == student.id, Submission.status.in_(['submitted', 'late', 'graded'])).count()
        missing = max(0, assigned - submitted)
        submission_rate = submitted / max(assigned, 1)
        slopes = [item for item in (attendance_trend['trend_slope'], assessment_trend['trend_slope']) if item is not None]
        rows.append({
            'student_id': student.student_id,
            'attendance': sum(imported_attendance) / len(imported_attendance) if imported_attendance else student.attendance,
            'assessment': sum(imported_assessment) / len(imported_assessment) if imported_assessment else student.assessment,
            'previous_gpa': student.previous_gpa,
            'current_gpa': student.current_gpa,
            'assignments_completed': student.assignments_completed,
            'activity_per_week': activity_per_week,
            'missing_submissions': missing,
            'attendance_change': attendance_trend['percent_change'] or 0.0,
            'assessment_change': assessment_trend['percent_change'] or 0.0,
            'momentum_score': sum(slopes) / len(slopes) if slopes else 0.0,
            TARGET: student.risk_level,
            'data_origin': 'DEMO DATA' if student.student_id.startswith('DEMO-') else 'INSTITUTIONAL IMPORT',
            'assignment_submission_rate': submission_rate,
        })
    return rows


def preprocess(output_path: Path = DEFAULT_OUTPUT) -> Path:
    with SessionLocal() as db:
        rows = build_rows(db)
    if not rows:
        raise ValueError('No students available. Run database migrations and import/seed student data first.')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(output_path, index=False)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description='Build the risk-model training CSV from database academic observations')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(f'Wrote processed dataset to {preprocess(args.output)}')


if __name__ == '__main__':
    main()