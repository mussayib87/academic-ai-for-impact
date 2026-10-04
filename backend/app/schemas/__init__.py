from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: str
    full_name: str
    email: str | None = None
    program: str | None = None
    year: str | None = None
    section: str | None = None
    department: str | None = None
    risk_level: str = 'LOW'
    risk_probability: float = Field(default=0.0, description='Probability of the predicted risk_level class.')
    risk_probability_semantics: str = 'P(risk_level)'
    class_probabilities: dict[str, float] = Field(default_factory=dict)
    previous_gpa: float = 0.0
    current_gpa: float = 0.0
    attendance: float = 0.0
    assessment: float = 0.0
    assignments_completed: float = 0.0
    momentum: float = 0.0


class StudentSelfOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: str
    full_name: str
    program: str | None = None
    year: str | None = None
    section: str | None = None
    department: str | None = None
    previous_gpa: float = 0.0
    current_gpa: float = 0.0
    attendance: float = 0.0
    assessment: float = 0.0
    assignments_completed: float = 0.0


class AssignmentCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    subject: str = Field(min_length=1, max_length=160)
    course: str | None = None
    section: str | None = None
    description: str | None = None
    instructions: str | None = None
    start_date: datetime | None = None
    due_date: datetime | None = None
    max_marks: float = Field(default=25, gt=0, le=100)
    status: str = Field(default='draft', pattern='^(draft|active|archived)$')
    allowed_file_types: list[str] = Field(default_factory=lambda: ['.pdf', '.docx', '.pptx', '.xlsx', '.txt', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.zip'])
    max_file_size: int = Field(default=10 * 1024 * 1024, gt=0, le=100 * 1024 * 1024)


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    subject: str
    subject_id: int | None = None
    course: str | None = None
    section: str | None = None
    description: str | None = None
    instructions: str | None = None
    start_date: datetime | None = None
    due_date: datetime | None = None
    max_marks: float = 100
    status: str
    allowed_file_types: list[str] = Field(default_factory=list)
    max_file_size: int


class SubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    assignment_id: int
    status: str
    file_name: str | None = None
    submitted_at: datetime | None = None
    grade: float | None = None
    feedback: str | None = None
    page_count: int = 1


class GradeRequest(BaseModel):
    grade: float = Field(default=0, ge=0, le=100)
    feedback: str | None = None
    rubric_scores: dict[int, float] = Field(default_factory=dict)


class RubricCriterionInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    maximum_score: float = Field(gt=0)


class RubricCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    criteria: list[RubricCriterionInput] = Field(min_length=1, max_length=30)


class AssignmentStatusUpdate(BaseModel):
    status: str = Field(pattern='^(draft|active|archived)$')


class RiskPredictionOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    student_id: str
    risk_level: str
    risk_probability: float
    model_version: str
    prediction_timestamp: datetime
    feature_contributions: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)