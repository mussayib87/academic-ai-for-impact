import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.database import SessionLocal
from backend.app.models import (
    AcademicMomentum,
    Assignment,
    AssignmentStudent,
    Attendance,
    Assessment,
    Course,
    InterventionDraft,
    LearningActivity,
    Mark,
    RiskSnapshot,
    Student,
    Submission,
    Subject,
    Teacher,
    User,
)
from backend.app.services.auth import hash_password

RISK_TARGETS = {'HIGH': 52, 'MEDIUM': 86, 'LOW': 110}


def seed_demo_data(db: Session) -> None:
    if db.query(User).filter(User.email == 'teacher@example.com').first():
        return
    rng = random.Random(20260929)
    subject = Subject(name='Academic Foundations', code='AF-101', department='Student Success')
    db.add(subject)
    db.flush()
    teacher_user = User(email='teacher@example.com', full_name='Dr. Maya Chen', role='TEACHER', password_hash=hash_password('teacher123'))
    db.add(teacher_user)
    db.flush()
    teacher = Teacher(user_id=teacher_user.id, department='Student Success')
    db.add(teacher)
    db.flush()
    course = Course(name='Academic Foundations', code='AF-101-A', section='A', subject_id=subject.id, teacher_id=teacher.id)
    db.add(course)
    db.flush()

    students: list[Student] = []
    risk_sequence = [level for level, count in RISK_TARGETS.items() for _ in range(count)]
    rng.shuffle(risk_sequence)
    departments = ['Engineering', 'Sciences', 'Humanities', 'Business']
    for index, risk in enumerate(risk_sequence, start=1):
        attendance = rng.uniform(55, 76) if risk == 'HIGH' else rng.uniform(72, 88) if risk == 'MEDIUM' else rng.uniform(88, 100)
        assessment = rng.uniform(42, 62) if risk == 'HIGH' else rng.uniform(58, 76) if risk == 'MEDIUM' else rng.uniform(74, 96)
        current_gpa = rng.uniform(1.6, 2.5) if risk == 'HIGH' else rng.uniform(2.3, 3.2) if risk == 'MEDIUM' else rng.uniform(3.0, 4.0)
        student = Student(
            student_id=f'DEMO-{index:04d}',
            full_name=f'Demo Student {index:03d}',
            email=f'student{index:03d}@demo.local',
            program='Academic Foundations',
            year=str(rng.randint(1, 4)),
            section=chr(65 + (index % 4)),
            department=departments[index % len(departments)],
            risk_level=risk,
            risk_probability=round(rng.uniform(0.72, 0.94) if risk == 'HIGH' else rng.uniform(0.42, 0.68) if risk == 'MEDIUM' else rng.uniform(0.05, 0.36), 3),
            previous_gpa=round(min(4.0, current_gpa + rng.uniform(-0.3, 0.6)), 2),
            current_gpa=round(current_gpa, 2),
            attendance=round(attendance, 1),
            assessment=round(assessment, 1),
            assignments_completed=rng.randint(1, 8),
            course_id=course.id,
        )
        students.append(student)
    db.add_all(students)
    db.flush()

    demo_user = User(email='student@example.com', full_name=students[0].full_name, role='STUDENT', password_hash=hash_password('student123'))
    db.add(demo_user)
    db.flush()
    students[0].user_id = demo_user.id

    now = datetime.utcnow()
    assignments = [
        Assignment(title='Study plan reflection', subject=subject.name, course=course.code, section=None, description='Reflect on your current study plan.', instructions='Describe one strategy you will try this week.', start_date=now - timedelta(days=3), due_date=now + timedelta(days=5), max_marks=100, status='active', allowed_file_types=['.pdf', '.docx', '.txt']),
        Assignment(title='Learning strategies review', subject=subject.name, course=course.code, section=None, description='Summarize the learning strategies covered in class.', instructions='Submit a short document.', start_date=now - timedelta(days=2), due_date=now + timedelta(days=9), max_marks=50, status='active', allowed_file_types=['.pdf', '.docx', '.txt']),
    ]
    db.add_all(assignments)
    db.flush()
    db.add_all([AssignmentStudent(assignment_id=assignment.id, student_id=student.id) for assignment in assignments for student in students])

    assessment = Assessment(course_id=course.id, title='Foundations assessment', due_at=now - timedelta(days=12), maximum_marks=100)
    db.add(assessment)
    db.flush()
    for student in students:
        for week in range(8):
            observed = now - timedelta(weeks=7 - week)
            trend = -1 if student.risk_level == 'HIGH' else -0.25 if student.risk_level == 'MEDIUM' else 0.2
            for metric, baseline, drift in (
                ('attendance', student.attendance + 10, trend * 2),
                ('assessment', student.assessment + 12, trend * 2.5),
                ('activity', rng.uniform(8, 20), trend),
                ('assignment_submission', rng.uniform(0.65, 1.0), trend / 10),
            ):
                value = max(0, min(100, baseline + drift * week + rng.uniform(-3, 3)))
                db.add(AcademicMomentum(student_id=student.id, metric=metric, value=round(value, 2), observed_at=observed))
            db.add(Attendance(student_id=student.id, course_id=course.id, observed_at=observed, attended=student.attendance >= 75, attendance_rate=student.attendance))
            db.add(LearningActivity(student_id=student.id, course_id=course.id, activity_type='weekly_learning_events', quantity=max(0, rng.gauss(14 if student.risk_level == 'LOW' else 9, 3)), occurred_at=observed))
            db.add(Mark(student_id=student.id, assessment_id=assessment.id, score=max(0, student.assessment + drift * week), recorded_at=observed))
        db.add(RiskSnapshot(student_id=student.id, risk_level=student.risk_level, probability=student.risk_probability, recorded_at=now - timedelta(days=1)))
    db.add(Submission(student_id=students[0].id, assignment_id=assignments[0].id, status='submitted', file_name='demo-reflection.pdf', submitted_at=now - timedelta(hours=3), grade=None))
    for student in [item for item in students if item.risk_level == 'HIGH'][:12]:
        db.add(InterventionDraft(student_id=student.id, title='Support check-in', body='AI-GENERATED DRAFT - FACULTY REVIEW REQUIRED\nPlease schedule a supportive academic check-in and discuss study resources.', status='draft', evidence={'demo_data': True, 'risk_level': student.risk_level}))
    db.commit()


def main() -> None:
    with SessionLocal() as db:
        seed_demo_data(db)
    print('Demo dataset ready: 248 fictional students (52 high, 86 medium, 110 low risk).')
    print('Demo logins: teacher@example.com / teacher123; student@example.com / student123')


if __name__ == '__main__':
    main()