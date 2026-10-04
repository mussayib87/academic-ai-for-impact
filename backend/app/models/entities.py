from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class User(Timestamps, Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(20), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    student: Mapped['Student | None'] = relationship(back_populates='user', uselist=False)
    teacher: Mapped['Teacher | None'] = relationship(back_populates='user', uselist=False)
    notifications: Mapped[list['Notification']] = relationship(back_populates='user', cascade='all, delete-orphan')


class Student(Timestamps, Base):
    __tablename__ = 'students'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), unique=True)
    student_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), index=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    program: Mapped[str | None] = mapped_column(String(160))
    year: Mapped[str | None] = mapped_column(String(30))
    section: Mapped[str | None] = mapped_column(String(40), index=True)
    department: Mapped[str | None] = mapped_column(String(160), index=True)
    risk_level: Mapped[str] = mapped_column(String(20), default='LOW', index=True)
    risk_probability: Mapped[float] = mapped_column(Float, default=0.0)
    previous_gpa: Mapped[float] = mapped_column(Float, default=0.0)
    current_gpa: Mapped[float] = mapped_column(Float, default=0.0)
    attendance: Mapped[float] = mapped_column(Float, default=0.0)
    assessment: Mapped[float] = mapped_column(Float, default=0.0)
    assignments_completed: Mapped[float] = mapped_column(Float, default=0.0)
    momentum: Mapped[float] = mapped_column(Float, default=0.0)
    course_id: Mapped[int | None] = mapped_column(ForeignKey('courses.id', ondelete='SET NULL'), index=True)
    course: Mapped['Course | None'] = relationship(back_populates='students')
    user: Mapped['User | None'] = relationship(back_populates='student')
    attendance_records: Mapped[list['Attendance']] = relationship(back_populates='student', cascade='all, delete-orphan')
    marks: Mapped[list['Mark']] = relationship(back_populates='student', cascade='all, delete-orphan')
    submissions: Mapped[list['Submission']] = relationship(back_populates='student', cascade='all, delete-orphan')
    momentum_observations: Mapped[list['AcademicMomentum']] = relationship(back_populates='student', cascade='all, delete-orphan')
    risk_snapshots: Mapped[list['RiskSnapshot']] = relationship(back_populates='student', cascade='all, delete-orphan')


class Teacher(Timestamps, Base):
    __tablename__ = 'teachers'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), unique=True)
    department: Mapped[str | None] = mapped_column(String(160))
    user: Mapped[User] = relationship(back_populates='teacher')
    courses: Mapped[list['Course']] = relationship(back_populates='teacher')


class Subject(Timestamps, Base):
    __tablename__ = 'subjects'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    department: Mapped[str | None] = mapped_column(String(160))
    courses: Mapped[list['Course']] = relationship(back_populates='subject')


class StudentSubjectAcademicRecord(Timestamps, Base):
    __tablename__ = 'student_subject_academic_records'
    __table_args__ = (UniqueConstraint('student_id', 'subject_id', 'academic_period', name='uq_student_subject_period_record'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey('subjects.id', ondelete='RESTRICT'), index=True)
    academic_period: Mapped[str] = mapped_column(String(30), index=True)
    fa1: Mapped[float | None] = mapped_column(Float)
    fa1_observed_at: Mapped[datetime | None] = mapped_column(DateTime)
    fa2: Mapped[float | None] = mapped_column(Float)
    fa2_observed_at: Mapped[datetime | None] = mapped_column(DateTime)
    assignment_mark: Mapped[float | None] = mapped_column(Float)
    assignment_observed_at: Mapped[datetime | None] = mapped_column(DateTime)
    attendance_rate: Mapped[float | None] = mapped_column(Float)
    attendance_observed_at: Mapped[datetime | None] = mapped_column(DateTime)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey('academic_data_import_batches.id', ondelete='SET NULL'), index=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    student: Mapped[Student] = relationship()
    subject: Mapped[Subject] = relationship()
    updated_by: Mapped[User | None] = relationship()


class StudentSubjectAcademicRecordHistory(Timestamps, Base):
    __tablename__ = 'student_subject_academic_record_history'

    id: Mapped[int] = mapped_column(primary_key=True)
    academic_record_id: Mapped[int] = mapped_column(ForeignKey('student_subject_academic_records.id', ondelete='CASCADE'), index=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey('academic_data_import_batches.id', ondelete='SET NULL'), index=True)
    changed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    change_kind: Mapped[str] = mapped_column(String(20))
    fa1: Mapped[float | None] = mapped_column(Float)
    fa1_observed_at: Mapped[datetime | None] = mapped_column(DateTime)
    fa2: Mapped[float | None] = mapped_column(Float)
    fa2_observed_at: Mapped[datetime | None] = mapped_column(DateTime)
    assignment_mark: Mapped[float | None] = mapped_column(Float)
    assignment_observed_at: Mapped[datetime | None] = mapped_column(DateTime)
    attendance_rate: Mapped[float | None] = mapped_column(Float)
    attendance_observed_at: Mapped[datetime | None] = mapped_column(DateTime)
    record: Mapped[StudentSubjectAcademicRecord] = relationship()
    import_batch: Mapped['AcademicDataImportBatch | None'] = relationship()
    changed_by: Mapped[User | None] = relationship()


class AcademicRiskOutcome(Timestamps, Base):
    __tablename__ = 'academic_risk_outcomes'
    __table_args__ = (UniqueConstraint('student_id', 'academic_period', name='uq_student_academic_period_risk_outcome'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), index=True)
    academic_period: Mapped[str] = mapped_column(String(30), index=True)
    risk_level: Mapped[str] = mapped_column(String(20))
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    outcome_source: Mapped[str] = mapped_column(String(255))
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey('academic_data_import_batches.id', ondelete='SET NULL'), index=True)
    recorded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    student: Mapped[Student] = relationship()
    import_batch: Mapped['AcademicDataImportBatch | None'] = relationship()
    recorded_by: Mapped[User | None] = relationship()


class Course(Timestamps, Base):
    __tablename__ = 'courses'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    section: Mapped[str | None] = mapped_column(String(40))
    subject_id: Mapped[int | None] = mapped_column(ForeignKey('subjects.id', ondelete='SET NULL'))
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey('teachers.id', ondelete='SET NULL'))
    students: Mapped[list[Student]] = relationship(back_populates='course')
    subject: Mapped['Subject | None'] = relationship(back_populates='courses')
    teacher: Mapped['Teacher | None'] = relationship(back_populates='courses')
    assessments: Mapped[list['Assessment']] = relationship(back_populates='course', cascade='all, delete-orphan')
    attendance_records: Mapped[list['Attendance']] = relationship(back_populates='course')


class Attendance(Timestamps, Base):
    __tablename__ = 'attendance'
    __table_args__ = (Index('ix_attendance_student_date', 'student_id', 'observed_at'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey('academic_data_import_batches.id', ondelete='SET NULL'), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey('courses.id', ondelete='SET NULL'))
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    attended: Mapped[bool] = mapped_column(Boolean)
    attendance_rate: Mapped[float | None] = mapped_column(Float)
    student: Mapped[Student] = relationship(back_populates='attendance_records')
    course: Mapped['Course | None'] = relationship(back_populates='attendance_records')


class Assessment(Timestamps, Base):
    __tablename__ = 'assessments'

    id: Mapped[int] = mapped_column(primary_key=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey('academic_data_import_batches.id', ondelete='SET NULL'), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey('courses.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    maximum_marks: Mapped[float] = mapped_column(Float, default=100.0)
    course: Mapped[Course] = relationship(back_populates='assessments')
    marks: Mapped[list['Mark']] = relationship(back_populates='assessment', cascade='all, delete-orphan')


class Mark(Timestamps, Base):
    __tablename__ = 'marks'
    __table_args__ = (Index('ix_marks_student_date', 'student_id', 'recorded_at'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey('academic_data_import_batches.id', ondelete='SET NULL'), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey('assessments.id', ondelete='CASCADE'), index=True)
    score: Mapped[float] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    student: Mapped[Student] = relationship(back_populates='marks')
    assessment: Mapped[Assessment] = relationship(back_populates='marks')


class LearningActivity(Timestamps, Base):
    __tablename__ = 'learning_activities'
    __table_args__ = (Index('ix_learning_activity_student_date', 'student_id', 'occurred_at'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey('academic_data_import_batches.id', ondelete='SET NULL'), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey('courses.id', ondelete='SET NULL'))
    activity_type: Mapped[str] = mapped_column(String(80))
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    student: Mapped[Student] = relationship()
    course: Mapped['Course | None'] = relationship()


class Assignment(Timestamps, Base):
    __tablename__ = 'assignments'

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(160))
    course: Mapped[str | None] = mapped_column(String(100), index=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey('subjects.id', ondelete='SET NULL'), index=True)
    section: Mapped[str | None] = mapped_column(String(40), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    instructions: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[datetime | None] = mapped_column(DateTime)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    max_marks: Mapped[float] = mapped_column(Float, default=100.0)
    status: Mapped[str] = mapped_column(String(20), default='draft', index=True)
    allowed_file_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    max_file_size: Mapped[int] = mapped_column(Integer, default=10 * 1024 * 1024)
    attachment_path: Mapped[str | None] = mapped_column(String(512))
    rubric_id: Mapped[int | None] = mapped_column(ForeignKey('rubrics.id', ondelete='SET NULL'))
    rubric: Mapped['Rubric | None'] = relationship(back_populates='assignments')
    subject_record: Mapped['Subject | None'] = relationship()
    enrollments: Mapped[list['AssignmentStudent']] = relationship(back_populates='assignment', cascade='all, delete-orphan')
    submissions: Mapped[list['Submission']] = relationship(back_populates='assignment', cascade='all, delete-orphan')


class AssignmentStudent(Timestamps, Base):
    __tablename__ = 'assignment_students'
    __table_args__ = (Index('ix_assignment_student_unique', 'assignment_id', 'student_id', unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey('assignments.id', ondelete='CASCADE'))
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'))
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    assignment: Mapped[Assignment] = relationship(back_populates='enrollments')
    student: Mapped[Student] = relationship()


class Submission(Timestamps, Base):
    __tablename__ = 'submissions'
    __table_args__ = (Index('ix_submission_student_assignment', 'student_id', 'assignment_id', unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), index=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey('assignments.id', ondelete='CASCADE'), index=True)
    status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    page_count: Mapped[int] = mapped_column(Integer, default=1)
    file_name: Mapped[str | None] = mapped_column(String(255))
    stored_path: Mapped[str | None] = mapped_column(String(512))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    grade: Mapped[float | None] = mapped_column(Float)
    feedback: Mapped[str | None] = mapped_column(Text)
    student: Mapped[Student] = relationship(back_populates='submissions')
    assignment: Mapped[Assignment] = relationship(back_populates='submissions')
    versions: Mapped[list['SubmissionVersion']] = relationship(back_populates='submission', cascade='all, delete-orphan')
    rubric_scores: Mapped[list['RubricScore']] = relationship(cascade='all, delete-orphan')
    feedback_items: Mapped[list['Feedback']] = relationship(cascade='all, delete-orphan')


class SubmissionVersion(Timestamps, Base):
    __tablename__ = 'submission_versions'

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey('submissions.id', ondelete='CASCADE'), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int] = mapped_column(Integer, default=1)
    page_count: Mapped[int] = mapped_column(Integer, default=1)
    file_name: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(512))
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    submission: Mapped[Submission] = relationship(back_populates='versions')


class Rubric(Timestamps, Base):
    __tablename__ = 'rubrics'

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    criteria: Mapped[list['RubricCriterion']] = relationship(back_populates='rubric', cascade='all, delete-orphan')
    assignments: Mapped[list['Assignment']] = relationship(back_populates='rubric')


class RubricCriterion(Timestamps, Base):
    __tablename__ = 'rubric_criteria'

    id: Mapped[int] = mapped_column(primary_key=True)
    rubric_id: Mapped[int] = mapped_column(ForeignKey('rubrics.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(160))
    maximum_score: Mapped[float] = mapped_column(Float)
    rubric: Mapped[Rubric] = relationship(back_populates='criteria')


class RubricScore(Timestamps, Base):
    __tablename__ = 'rubric_scores'

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey('submissions.id', ondelete='CASCADE'), index=True)
    criterion_id: Mapped[int] = mapped_column(ForeignKey('rubric_criteria.id', ondelete='CASCADE'))
    score: Mapped[float] = mapped_column(Float)
    feedback: Mapped[str | None] = mapped_column(Text)
    submission: Mapped[Submission] = relationship(back_populates='rubric_scores')
    criterion: Mapped[RubricCriterion] = relationship()


class Feedback(Timestamps, Base):
    __tablename__ = 'feedback'

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey('submissions.id', ondelete='CASCADE'), index=True)
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey('teachers.id', ondelete='SET NULL'))
    body: Mapped[str] = mapped_column(Text)
    submission: Mapped[Submission] = relationship(back_populates='feedback_items')
    teacher: Mapped['Teacher | None'] = relationship()


class RiskPrediction(Timestamps, Base):
    __tablename__ = 'risk_predictions'

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), index=True)
    risk_level: Mapped[str] = mapped_column(String(20), index=True)
    probability: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(80))
    prediction_timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    input_features: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    student: Mapped[Student] = relationship()
    explanation: Mapped['ShapExplanation | None'] = relationship(back_populates='prediction', uselist=False, cascade='all, delete-orphan')


class RiskSnapshot(Timestamps, Base):
    __tablename__ = 'risk_snapshots'

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), index=True)
    risk_level: Mapped[str] = mapped_column(String(20), index=True)
    probability: Mapped[float] = mapped_column(Float, default=0.0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    student: Mapped[Student] = relationship(back_populates='risk_snapshots')


class ModelRegistryEntry(Timestamps, Base):
    __tablename__ = 'model_registry'

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, default='risk-production')
    model_version: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    model_type: Mapped[str] = mapped_column(String(40), default='classification', index=True)
    feature_schema: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    feature_contract_version: Mapped[str | None] = mapped_column(String(80), default=None)
    training_period: Mapped[str | None] = mapped_column(String(40), default=None)
    training_dataset_version: Mapped[str | None] = mapped_column(String(160), default=None)
    training_dataset_hash: Mapped[str | None] = mapped_column(String(128), default=None)
    training_timestamp: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    validation_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    artifact_identifier: Mapped[str | None] = mapped_column(String(512), default=None)
    artifact_hash: Mapped[str | None] = mapped_column(String(128), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    status: Mapped[str] = mapped_column(String(20), default='candidate', index=True)
    deployment_status: Mapped[str] = mapped_column(String(20), default='SHADOW', index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    dataset_id: Mapped[str | None] = mapped_column(String(80), default=None, index=True)
    dataset_version: Mapped[str | None] = mapped_column(String(80), default=None)
    dataset_fingerprint: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    target_definition: Mapped[str | None] = mapped_column(Text, default=None)
    aggregation_strategy: Mapped[str | None] = mapped_column(Text, default=None)
    training_periods: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    validation_periods: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    test_periods: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    algorithm: Mapped[str | None] = mapped_column(String(80), default=None)
    hyperparameters: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    random_seed: Mapped[int | None] = mapped_column(Integer, default=None)
    validation_status: Mapped[str | None] = mapped_column(String(30), default=None)
    approval_status: Mapped[str | None] = mapped_column(String(30), default=None)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    previous_production_model_version: Mapped[str | None] = mapped_column(String(80), default=None)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    rejected_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True, default=None)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    rejection_reason: Mapped[str | None] = mapped_column(Text, default=None)


class ModelDeploymentState(Base):
    __tablename__ = 'model_deployment_state'

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    active_model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    active_artifact_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class ModelDeploymentEvent(Base):
    __tablename__ = 'model_deployment_events'

    id: Mapped[int] = mapped_column(primary_key=True)
    event: Mapped[str] = mapped_column(String(30), index=True)
    previous_version: Mapped[str | None] = mapped_column(String(80))
    new_version: Mapped[str | None] = mapped_column(String(80))
    candidate_version: Mapped[str | None] = mapped_column(String(80), index=True)
    artifact_hash: Mapped[str | None] = mapped_column(String(128))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    actor_role: Mapped[str] = mapped_column(String(20))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), index=True)
    rollback_of_event_id: Mapped[int | None] = mapped_column(ForeignKey('model_deployment_events.id', ondelete='SET NULL'))
    dataset_hash: Mapped[str | None] = mapped_column(String(128))
    feature_contract: Mapped[list[str] | None] = mapped_column(JSON)
    evaluation_reference: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    previous_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    new_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class Phase3PolicyApproval(Base):
    __tablename__ = 'phase3_policy_approvals'

    id: Mapped[int] = mapped_column(primary_key=True)
    aggregation_strategy: Mapped[str] = mapped_column(String(80), nullable=False)
    feature_contract: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    approval_note: Mapped[str] = mapped_column(Text, nullable=False)


@event.listens_for(ModelDeploymentEvent, 'before_update')
def prevent_deployment_event_update(mapper, connection, target) -> None:
    raise ValueError('Model deployment events are immutable.')


@event.listens_for(ModelDeploymentEvent, 'before_delete')
def prevent_deployment_event_delete(mapper, connection, target) -> None:
    raise ValueError('Model deployment events are immutable.')


@event.listens_for(Phase3PolicyApproval, 'before_update')
def prevent_phase3_policy_approval_update(mapper, connection, target) -> None:
    raise ValueError('Phase 3 policy approval records are immutable.')


@event.listens_for(Phase3PolicyApproval, 'before_delete')
def prevent_phase3_policy_approval_delete(mapper, connection, target) -> None:
    raise ValueError('Phase 3 policy approval records are immutable.')


class ShapExplanation(Timestamps, Base):
    __tablename__ = 'shap_explanations'

    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey('risk_predictions.id', ondelete='CASCADE'), index=True)
    values: Mapped[dict[str, float]] = mapped_column(JSON)
    base_value: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(80))
    prediction: Mapped[RiskPrediction] = relationship(back_populates='explanation')


class AcademicMomentum(Timestamps, Base):
    __tablename__ = 'academic_momentum'
    __table_args__ = (Index('ix_momentum_student_metric_date', 'student_id', 'metric', 'observed_at'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), index=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey('academic_data_import_batches.id', ondelete='SET NULL'), index=True)
    metric: Mapped[str] = mapped_column(String(40), index=True)
    value: Mapped[float] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    classification: Mapped[str | None] = mapped_column(String(20))
    trend_slope: Mapped[float | None] = mapped_column(Float)
    percent_change: Mapped[float | None] = mapped_column(Float)
    student: Mapped[Student] = relationship(back_populates='momentum_observations')


class AcademicDataImportBatch(Timestamps, Base):
    __tablename__ = 'academic_data_import_batches'
    __table_args__ = (UniqueConstraint('dataset_type', 'file_checksum', name='uq_academic_import_type_checksum'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_type: Mapped[str] = mapped_column(String(40), index=True)
    source_filename: Mapped[str] = mapped_column(String(255))
    file_checksum: Mapped[str] = mapped_column(String(64))
    imported_by_user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'), index=True)
    imported_rows: Mapped[int] = mapped_column(Integer, default=0)
    rejected_rows: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0)
    validation_errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class AcademicDataImportRow(Timestamps, Base):
    __tablename__ = 'academic_data_import_rows'
    __table_args__ = (UniqueConstraint('dataset_type', 'row_checksum', name='uq_academic_import_type_row'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('academic_data_import_batches.id', ondelete='CASCADE'), index=True)
    dataset_type: Mapped[str] = mapped_column(String(40), index=True)
    row_checksum: Mapped[str] = mapped_column(String(64))
    row_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    student_id: Mapped[int | None] = mapped_column(ForeignKey('students.id', ondelete='SET NULL'), index=True)
    academic_record_id: Mapped[int | None] = mapped_column(ForeignKey('student_subject_academic_records.id', ondelete='SET NULL'), index=True)
    errors: Mapped[list[str]] = mapped_column(JSON, default=list)


class Intervention(Timestamps, Base):
    __tablename__ = 'interventions'

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), index=True)
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey('teachers.id', ondelete='SET NULL'))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='approved', index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    outcome: Mapped[str | None] = mapped_column(String(40), default=None)
    outcome_notes: Mapped[str | None] = mapped_column(Text, default=None)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    student: Mapped[Student] = relationship()
    teacher: Mapped['Teacher | None'] = relationship()


class InterventionDraft(Timestamps, Base):
    __tablename__ = 'intervention_drafts'

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='draft', index=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    student: Mapped[Student] = relationship()
    reviews: Mapped[list['InterventionReview']] = relationship(cascade='all, delete-orphan')


class SupportAction(Timestamps, Base):
    __tablename__ = 'support_actions'

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), index=True)
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey('teachers.id', ondelete='SET NULL'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    action_type: Mapped[str] = mapped_column(String(50), default='GENERAL_SUPPORT')
    status: Mapped[str] = mapped_column(String(40), default='PENDING_FACULTY_REVIEW', index=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(String(200), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    student: Mapped[Student] = relationship()
    teacher: Mapped['Teacher | None'] = relationship()


class SupportFollowUp(Timestamps, Base):
    __tablename__ = 'support_follow_ups'

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), index=True)
    assigned_to: Mapped[str] = mapped_column(String(200))
    scheduled_date: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default='SCHEDULED', index=True)
    outcome: Mapped[str | None] = mapped_column(String(200))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    student: Mapped[Student] = relationship()


class SupportPlanVersion(Timestamps, Base):
    __tablename__ = 'support_plan_versions'

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id', ondelete='CASCADE'), index=True)
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey('teachers.id', ondelete='SET NULL'), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, index=True)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    student: Mapped[Student] = relationship()
    teacher: Mapped['Teacher | None'] = relationship()


class InterventionReview(Timestamps, Base):
    __tablename__ = 'intervention_reviews'

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey('intervention_drafts.id', ondelete='CASCADE'), index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey('teachers.id', ondelete='CASCADE'))
    decision: Mapped[str] = mapped_column(String(20))
    comments: Mapped[str | None] = mapped_column(Text)
    draft: Mapped[InterventionDraft] = relationship(back_populates='reviews')
    teacher: Mapped[Teacher] = relationship()


class RagDocument(Timestamps, Base):
    __tablename__ = 'rag_documents'

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(512), unique=True)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    chunks: Mapped[list['RagChunk']] = relationship(back_populates='document', cascade='all, delete-orphan')


class RagChunk(Timestamps, Base):
    __tablename__ = 'rag_chunks'

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey('rag_documents.id', ondelete='CASCADE'), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(JSON)
    document: Mapped[RagDocument] = relationship(back_populates='chunks')


class Notification(Timestamps, Base):
    __tablename__ = 'notifications'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    user: Mapped[User] = relationship(back_populates='notifications')


class AuditLog(Timestamps, Base):
    __tablename__ = 'audit_logs'

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(80))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)