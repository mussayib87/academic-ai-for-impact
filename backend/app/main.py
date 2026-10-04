from datetime import datetime, timedelta, timezone
import hashlib
import csv
import io
import json
import math
import mimetypes
from pathlib import Path
from typing import Any

from ai.risk.features import FEATURE_CONTRACT_VERSION, FEATURES
from ai.explainability.service import explain_student, global_importance
from ai.llm.grounding import validate_intervention_draft
from ai.llm.provider import InterventionContext, build_provider
from ai.risk.predict import DEFAULT_ARTIFACT, load_artifact, predict as predict_risk
from ai.rag.index import retrieve
from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.auth import router as auth_router
from backend.app.config import BASE_DIR, get_settings
from backend.app.core.security import CurrentStudent, CurrentTeacher, CurrentUser, get_current_user
from backend.app.database import get_db
from backend.app.models import (
    AcademicMomentum,
    AcademicDataImportBatch,
    AcademicDataImportRow,
    AcademicRiskOutcome,
    Assessment,
    Assignment,
    AssignmentStudent,
    Attendance,
    AuditLog,
    Course,
    Intervention,
    InterventionDraft,
    InterventionReview,
    ModelDeploymentEvent,
    ModelDeploymentState,
    ModelRegistryEntry,
    Phase3PolicyApproval,
    Notification,
    Mark,
    RiskPrediction,
    RiskSnapshot,
    RubricCriterion,
    Rubric,
    RubricScore,
    Student,
    StudentSubjectAcademicRecord,
    StudentSubjectAcademicRecordHistory,
    Subject,
    Submission,
    SubmissionVersion,
    SupportAction,
    SupportFollowUp,
    SupportPlanVersion,
    Teacher,
    User,
)
from backend.app.schemas import AssignmentCreate, AssignmentOut, AssignmentStatusUpdate, GradeRequest, RubricCreate, StudentOut, StudentSelfOut, SubmissionOut
from backend.app.schemas.academic import SubjectAcademicRecordUpdate
from backend.app.schemas.interventions import InterventionEditRequest, InterventionGenerateRequest
from backend.app.schemas.risk import ModelApprovalRequest, ModelPromotionRequest, ModelRegistryEntryInput, ModelRejectionRequest, ModelRollbackRequest, Phase3PolicyApprovalRequest, Phase3TrainingRequest, RiskFeatureInput, RiskSimulationInput
from backend.app.services.academic_records import SUBJECTS, academic_periods, academic_totals, build_register_row, normalize_academic_period, selected_academic_period, serialize_record, subject_records_by_student
from backend.app.services.uploads import store_submission
from backend.app.services.momentum import calculate_momentum
from backend.app.services.model_deployment import DeploymentArtifactError, active_artifact_path, candidate_artifact_path, sha256_file, verify_candidate_artifact
from backend.app.services.academic_imports import ImportValidationError, import_academic_data
from ai.risk.academic_dataset import DATASET_FIELDS, build_observation_rows, readiness_report
from ai.risk.phase3 import DATASET_FIELDS as PHASE3_DATASET_FIELDS, build_phase3_dataset
from ai.risk.candidate import explain_candidate, train_candidate

settings = get_settings()
CANDIDATE_ARTIFACT_DIRECTORY = BASE_DIR / 'models' / 'candidates'
app = FastAPI(title=settings.app_name, version='2.0.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
    allow_headers=['Authorization', 'Content-Type'],
)
app.include_router(auth_router, prefix=settings.api_v1_prefix)


def audit(db: Session, user: User, action: str, resource_type: str, resource_id: int | None = None) -> None:
    db.add(AuditLog(actor_user_id=user.id, action=action, resource_type=resource_type, resource_id=str(resource_id) if resource_id else None))


def phase3_audit(
    db: Session,
    user: User,
    action: str,
    *,
    result: str,
    reason: str | None = None,
    dataset_id: str | None = None,
    dataset_version: str | None = None,
    dataset_fingerprint: str | None = None,
    model_version: str | None = None,
    resource_id: int | None = None,
    previous_state: dict[str, Any] | None = None,
    new_state: dict[str, Any] | None = None,
) -> None:
    db.add(AuditLog(
        actor_user_id=user.id,
        action=action,
        resource_type='phase3_model_governance',
        resource_id=str(resource_id) if resource_id is not None else model_version,
        detail={
            'result': result,
            'reason': reason,
            'dataset_id': dataset_id,
            'dataset_version': dataset_version,
            'dataset_fingerprint': dataset_fingerprint,
            'model_version': model_version,
            'actor_role': user.role.upper(),
            'previous_state': previous_state,
            'new_state': new_state,
        },
    ))
    db.commit()


def phase3_public_report(dataset: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in dataset.items() if key not in {'rows', 'rejected_rows'}}


def student_user_id(db: Session, student_id: int) -> int:
    student = db.query(Student.user_id).filter(Student.id == student_id).first()
    return student[0] if student and student[0] else -1


def normalize_support_status(value: Any, *, default: str = 'PENDING_FACULTY_REVIEW') -> str:
    if value is None:
        return default
    text = str(value).strip().upper().replace(' ', '_')
    aliases = {
        'PENDING_REVIEW': 'PENDING_FACULTY_REVIEW',
        'PENDING_FACULTY_REVIEW': 'PENDING_FACULTY_REVIEW',
        'IN_PROGRESS': 'IN_PROGRESS',
        'PROGRESS': 'IN_PROGRESS',
        'COMPLETED': 'COMPLETED',
        'DONE': 'COMPLETED',
        'CANCELLED': 'CANCELLED',
        'CANCELED': 'CANCELLED',
        'MISSED': 'MISSED',
        'OVERDUE': 'OVERDUE',
        'SCHEDULED': 'SCHEDULED',
        'APPROVED': 'APPROVED',
        'REJECTED': 'REJECTED',
        'DRAFT': 'DRAFT',
    }
    return aliases.get(text, text)


def coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError:
            return None
    return None


def student_features(student: Student, db: Session) -> dict[str, float]:
    observations = db.query(AcademicMomentum).filter(AcademicMomentum.student_id == student.id).order_by(AcademicMomentum.observed_at, AcademicMomentum.id).all()
    grouped: dict[str, list[float]] = {}
    for observation in observations:
        grouped.setdefault(observation.metric, []).append(observation.value)
    attendance_trend = calculate_momentum(grouped.get('attendance', []))
    assessment_trend = calculate_momentum(grouped.get('assessment', []))
    activities = db.query(AcademicMomentum).filter(AcademicMomentum.student_id == student.id, AcademicMomentum.metric == 'activity').order_by(AcademicMomentum.observed_at, AcademicMomentum.id).all()
    activity_average = sum(item.value for item in activities[-4:]) / max(1, len(activities[-4:]))
    assigned = db.query(AssignmentStudent.id).filter(AssignmentStudent.student_id == student.id).count()
    submitted = db.query(Submission.id).filter(Submission.student_id == student.id, Submission.status.in_(['submitted', 'late', 'graded'])).count()
    slopes = [value for value in (attendance_trend['trend_slope'], assessment_trend['trend_slope']) if value is not None]
    imported_attendance = [item.value for item in observations if item.metric == 'attendance' and item.import_batch_id is not None]
    imported_assessment = [item.value for item in observations if item.metric == 'assessment' and item.import_batch_id is not None]
    return {
        'attendance': sum(imported_attendance) / len(imported_attendance) if imported_attendance else student.attendance,
        'assessment': sum(imported_assessment) / len(imported_assessment) if imported_assessment else student.assessment,
        'previous_gpa': student.previous_gpa,
        'current_gpa': student.current_gpa,
        'assignments_completed': student.assignments_completed,
        'activity_per_week': activity_average,
        'missing_submissions': float(max(0, assigned - submitted)),
        'attendance_change': float(attendance_trend['percent_change'] or 0),
        'assessment_change': float(assessment_trend['percent_change'] or 0),
        'momentum_score': sum(slopes) / len(slopes) if slopes else 0.0,
    }


def student_risk_view(student: Student, db: Session) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        features = student_features(student, db)
        prediction = predict_with_active_model(features, db)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail='Risk model is not trained. Run the documented training command first.') from exc
    student_data = StudentOut.model_validate(student).model_dump()
    student_data.update({
        'attendance': features['attendance'],
        'assessment': features['assessment'],
        'assignments_completed': features['assignments_completed'],
        'risk_level': prediction['risk_level'],
        'risk_probability': prediction['risk_probability'],
        'risk_probability_semantics': prediction['risk_probability_semantics'],
        'class_probabilities': prediction['class_probabilities'],
    })
    return student_data, prediction


def model_feature_schema() -> list[str]:
    try:
        artifact = load_artifact()
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=503, detail='The production risk model or its feature metadata is unavailable.') from exc
    metadata = artifact.get('metadata', {})
    features = metadata.get('features')
    if not isinstance(features, list):
        features = getattr(artifact.get('pipeline'), 'feature_names_in_', None)
        features = features.tolist() if features is not None else None
    if not isinstance(features, list) or set(features) != set(FEATURES):
        raise HTTPException(status_code=503, detail='The production model feature contract does not match the supported prediction contract.')
    return [str(name) for name in features]


def production_model_registry_entry() -> dict[str, Any]:
    try:
        artifact = load_artifact()
        artifact_hash = hashlib.sha256(DEFAULT_ARTIFACT.read_bytes()).hexdigest()
    except (FileNotFoundError, KeyError, ValueError, OSError) as exc:
        raise HTTPException(status_code=503, detail='The production risk model is unavailable for registry inspection.') from exc
    metadata = artifact.get('metadata', {})
    dataset_path = metadata.get('dataset')
    return {
        'model_id': 'risk-production',
        'model_version': metadata.get('model_version'),
        'model_type': 'classification',
        'feature_contract_version': FEATURE_CONTRACT_VERSION,
        'feature_contract': model_feature_schema(),
        'training_dataset_version': Path(dataset_path).name if isinstance(dataset_path, str) and dataset_path else None,
        'training_dataset_hash': metadata.get('training_dataset_hash'),
        'training_provenance': {
            'source': Path(dataset_path).name if isinstance(dataset_path, str) and dataset_path else None,
            'demo_data': metadata.get('demo_data'),
            'training_rows': metadata.get('training_rows'),
            'evaluation_rows': metadata.get('evaluation_rows'),
        },
        'training_timestamp': metadata.get('trained_at'),
        'validation_metrics': metadata.get('evaluation'),
        'artifact_identifier': DEFAULT_ARTIFACT.name,
        'artifact_hash': artifact_hash,
        'status': 'production',
        'created_at': None,
        'notes': None,
    }


def selected_model_artifact(db: Session) -> Path:
    try:
        production = production_model_registry_entry()
        return active_artifact_path(
            db,
            candidate_directory=CANDIDATE_ARTIFACT_DIRECTORY,
            production_path=DEFAULT_ARTIFACT,
            production_version=str(production['model_version']),
            production_hash=str(production['artifact_hash']),
        )
    except DeploymentArtifactError as exc:
        raise HTTPException(status_code=503, detail=f'Active local model deployment is unsafe or unavailable: {exc}') from exc


def predict_with_active_model(features: dict[str, float], db: Session) -> dict[str, Any]:
    artifact_path = selected_model_artifact(db)
    return predict_risk(features) if artifact_path.resolve() == DEFAULT_ARTIFACT.resolve() else predict_risk(features, artifact_path)


def explain_with_active_model(features: dict[str, float], db: Session, *, target_class: str | None = None) -> dict[str, Any]:
    artifact_path = selected_model_artifact(db)
    return explain_student(features, target_class=target_class) if artifact_path.resolve() == DEFAULT_ARTIFACT.resolve() else explain_student(features, artifact_path, target_class=target_class)


def validate_simulation_scenario(scenario: dict[str, float]) -> dict[str, float]:
    supported = set(model_feature_schema())
    unsupported = sorted(set(scenario) - supported)
    if unsupported:
        raise HTTPException(status_code=422, detail={'message': 'Unsupported model feature(s).', 'features': unsupported})
    if not scenario:
        raise HTTPException(status_code=422, detail='Provide at least one supported model feature in the scenario payload.')
    bounds = {
        'attendance': (0.0, 100.0),
        'assessment': (0.0, 100.0),
        'previous_gpa': (0.0, 4.0),
        'current_gpa': (0.0, 4.0),
        'assignments_completed': (0.0, None),
        'activity_per_week': (0.0, None),
        'missing_submissions': (0.0, None),
    }
    validated: dict[str, float] = {}
    for feature, raw_value in scenario.items():
        value = float(raw_value)
        if not math.isfinite(value):
            raise HTTPException(status_code=422, detail=f'{feature} must be a finite number.')
        minimum, maximum = bounds.get(feature, (None, None))
        if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
            range_description = f'{minimum} to {maximum}' if maximum is not None else f'at least {minimum}'
            raise HTTPException(status_code=422, detail=f'{feature} must be {range_description}.')
        validated[feature] = value
    return validated


def simulate_student_risk(student: Student | None, db: Session, scenario: dict[str, float]) -> dict[str, Any]:
    if student is None:
        raise HTTPException(status_code=404, detail='Student not found')
    baseline_features = student_features(student, db)
    base_prediction = predict_with_active_model(baseline_features, db)
    scenario_values = validate_simulation_scenario(scenario)
    candidate = dict(baseline_features)
    candidate.update(scenario_values)
    simulated_prediction = predict_with_active_model(candidate, db)
    class_names = sorted(set(base_prediction['class_probabilities']) | set(simulated_prediction['class_probabilities']))
    probability_deltas = {
        name: round(simulated_prediction['class_probabilities'].get(name, 0.0) - base_prediction['class_probabilities'].get(name, 0.0), 8)
        for name in class_names
    }
    changed_features = [
        {'name': name, 'baseline_value': baseline_features[name], 'simulated_value': candidate[name]}
        for name in FEATURES
        if baseline_features[name] != candidate[name]
    ]
    unchanged_features = [name for name in FEATURES if baseline_features[name] == candidate[name]]
    simulation_timestamp = datetime.now(timezone.utc).isoformat()
    risk_delta = round(float(simulated_prediction['risk_probability']) - float(base_prediction['risk_probability']), 8)
    class_delta = simulated_prediction['risk_level'] if simulated_prediction['risk_level'] != base_prediction['risk_level'] else None
    return {
        'student_id': student.id,
        'baseline_prediction': base_prediction,
        'simulated_prediction': simulated_prediction,
        'baseline_class_probabilities': base_prediction['class_probabilities'],
        'simulated_class_probabilities': simulated_prediction['class_probabilities'],
        'baseline_risk_level': base_prediction['risk_level'],
        'simulated_risk_level': simulated_prediction['risk_level'],
        'probability_deltas': probability_deltas,
        'changed_features': changed_features,
        'unchanged_features': unchanged_features,
        'model_version': base_prediction['model_version'],
        'simulation_timestamp': simulation_timestamp,
        'risk_delta': risk_delta,
        'class_delta': class_delta,
        'scenario_applied': scenario_values,
        'simulation_label': 'SIMULATION / WHAT-IF - NOT AN ACTUAL STUDENT PREDICTION',
    }


def compute_data_quality_report(db: Session) -> dict[str, Any]:
    now = datetime.utcnow()
    stale_before = now - timedelta(days=180)
    records = db.query(StudentSubjectAcademicRecord).all()
    outcomes = db.query(AcademicRiskOutcome).all()
    import_rows = db.query(AcademicDataImportRow).all()
    outcome_by_key = {(item.student_id, item.academic_period): item for item in outcomes}
    temporal_problems = 0
    stale_observation_records = 0
    future_dated_records = 0
    missing_observation_dates = 0
    complete_observations = 0
    for record in records:
        dated_values = (
            (record.fa1, record.fa1_observed_at),
            (record.fa2, record.fa2_observed_at),
            (record.assignment_mark, record.assignment_observed_at),
            (record.attendance_rate, record.attendance_observed_at),
        )
        outcome = outcome_by_key.get((record.student_id, record.academic_period))
        if all(value is not None and observed_at is not None for value, observed_at in dated_values):
            complete_observations += 1
        present_dates = [observed_at for value, observed_at in dated_values if value is not None and observed_at is not None]
        if any(observed_at < stale_before for observed_at in present_dates):
            stale_observation_records += 1
        if any(observed_at > now for observed_at in present_dates):
            future_dated_records += 1
        if any(value is not None and observed_at is None for value, observed_at in dated_values):
            missing_observation_dates += 1
        if outcome is not None and any(value is not None and (observed_at is None or observed_at > outcome.observed_at) for value, observed_at in dated_values):
            temporal_problems += 1

    unmatched_student_rows = sum(any('unknown student_id:' in error.casefold() or 'ambiguous student_id:' in error.casefold() for error in (row.errors or [])) for row in import_rows)
    unmatched_subject_rows = sum(any('unknown subject_code:' in error.casefold() for error in (row.errors or [])) for row in import_rows)
    academic_period_problems = sum(
        record.academic_period == 'UNSPECIFIED' for record in records
    ) + sum(any('academic_period' in error.casefold() for error in (row.errors or [])) for row in import_rows)
    readiness = readiness_report(db)
    record_count = len(records)
    aligned_count = readiness['complete_period_aligned_observations_with_valid_target']
    fa1_count = sum(record.fa1 is not None for record in records)
    fa2_count = sum(record.fa2 is not None for record in records)
    missing_values = {
        'fa1': record_count - fa1_count,
        'fa2': record_count - fa2_count,
        'assignment_mark': sum(record.assignment_mark is None for record in records),
        'attendance_rate': sum(record.attendance_rate is None for record in records),
    }
    invalid_ranges = readiness['invalid_values']
    invalid_count = sum(invalid_ranges.values())
    severe = invalid_count > 0 or readiness['duplicate_record_groups'] > 0 or readiness['duplicate_outcome_groups'] > 0 or temporal_problems > 0 or future_dated_records > 0
    has_warnings = (
        any(missing_values.values()) or unmatched_student_rows > 0 or unmatched_subject_rows > 0
        or academic_period_problems > 0 or stale_observation_records > 0 or missing_observation_dates > 0
    )
    status = 'critical' if severe else 'warning' if has_warnings or record_count == 0 else 'healthy'
    return {
        'status': status,
        'generated_at': now.isoformat(),
        'counts': {
            'students': db.query(Student.id).count(),
            'subject_records': record_count,
            'risk_outcomes': len(outcomes),
            'records_with_aligned_outcomes': aligned_count,
            'complete_observations': complete_observations,
            'duplicate_record_groups': readiness['duplicate_record_groups'],
            'duplicate_outcome_groups': readiness['duplicate_outcome_groups'],
        },
        'coverage': {
            'fa1_count': fa1_count,
            'fa1_percent': fa1_count / record_count * 100 if record_count else None,
            'fa2_count': fa2_count,
            'fa2_percent': fa2_count / record_count * 100 if record_count else None,
            'complete_observations_percent': complete_observations / record_count * 100 if record_count else None,
            'outcome_alignment_percent': aligned_count / record_count * 100 if record_count else None,
        },
        'missing_values': missing_values,
        'invalid_ranges': invalid_ranges,
        'checks': {
            'unmatched_student_rows': unmatched_student_rows,
            'unmatched_subject_rows': unmatched_subject_rows,
            'academic_period_problems': academic_period_problems,
            'stale_observation_records_180d': stale_observation_records,
            'future_dated_records': future_dated_records,
            'missing_observation_timestamps': missing_observation_dates,
            'temporal_alignment_problems': temporal_problems,
            'import_rows_with_errors': sum(bool(row.errors) for row in import_rows),
        },
        'readiness': readiness,
        'notes': 'The academic-data gate requires period-matched independent outcomes and temporal alignment. Demo-model metrics are excluded from readiness; inspect import provenance before treating academic-record coverage as real-world evidence.',
    }


def risk_transition_report(db: Session) -> dict[str, Any]:
    students = db.query(Student).order_by(Student.id).all()
    histories: dict[int, list[RiskPrediction]] = {student.id: [] for student in students}
    for prediction in db.query(RiskPrediction).order_by(RiskPrediction.student_id, RiskPrediction.prediction_timestamp, RiskPrediction.id).all():
        histories.setdefault(prediction.student_id, []).append(prediction)
    insufficient = [student.id for student in students if len(histories.get(student.id, [])) < 2]
    transitions = []
    for student in students:
        history = histories.get(student.id, [])
        for previous, current in zip(history, history[1:]):
            if previous.risk_level == current.risk_level:
                continue
            transitions.append({
                'student_id': student.id,
                'student_name': student.full_name,
                'previous_risk': previous.risk_level,
                'new_risk': current.risk_level,
                'recorded_at': current.prediction_timestamp.isoformat(),
                'previous_probability': previous.probability,
                'new_probability': current.probability,
                'probability_delta': round(current.probability - previous.probability, 8),
                'probability_note': 'Difference between the saved winning-class probabilities; classes may differ.',
                'previous_model_version': previous.model_version,
                'model_version': current.model_version,
                'evidence': {'previous_prediction_id': previous.id, 'prediction_id': current.id},
            })
    return {
        'history_status': 'available' if any(len(items) >= 2 for items in histories.values()) else 'insufficient_history',
        'students_with_insufficient_history': insufficient,
        'transitions': transitions,
    }


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


@app.get(f'{settings.api_v1_prefix}/ml/academic-data/readiness')
def academic_ml_readiness(user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    return readiness_report(db)


@app.get(f'{settings.api_v1_prefix}/ml/academic-data/export.csv')
def export_academic_ml_observations(user: CurrentTeacher, db: Session = Depends(get_db)) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=DATASET_FIELDS)
    writer.writeheader()
    writer.writerows(build_observation_rows(db))
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="academic-ml-observations.csv"'})


@app.post(f'{settings.api_v1_prefix}/academic-data/import')
async def upload_academic_data(
    user: CurrentTeacher,
    dataset_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    content = await file.read(settings.max_upload_size + 1)
    await file.close()
    if len(content) > settings.max_upload_size:
        raise HTTPException(status_code=413, detail=f'File exceeds the {settings.max_upload_size}-byte upload limit.')
    try:
        result = import_academic_data(db, user_id=user.id, filename=file.filename or '', content=content, dataset_type=dataset_type)
    except ImportValidationError as exc:
        raise HTTPException(status_code=422, detail={'message': str(exc), 'validation_errors': exc.errors}) from exc
    audit(db, user, 'academic_data.imported', 'academic_data_import_batch', result.get('batch_id'))
    if not result.get('duplicate_import'):
        db.commit()
    return result


@app.get(f'{settings.api_v1_prefix}/academic-data/imports')
def list_academic_imports(user: CurrentTeacher, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    batches = db.query(AcademicDataImportBatch).order_by(AcademicDataImportBatch.created_at.desc()).limit(50).all()
    return [{
        'id': batch.id,
        'dataset_type': batch.dataset_type,
        'source_filename': batch.source_filename,
        'imported_rows': batch.imported_rows,
        'rejected_rows': batch.rejected_rows,
        'duplicate_rows': batch.duplicate_rows,
        'created_at': batch.created_at.isoformat(),
    } for batch in batches]


@app.get(f'{settings.api_v1_prefix}/subjects')
def list_subjects(user: CurrentTeacher, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    subjects = db.query(Subject).filter(Subject.code.in_(SUBJECTS)).order_by(Subject.code).all()
    return [{'id': subject.id, 'code': subject.code, 'name': subject.name} for subject in subjects]


@app.get(f'{settings.api_v1_prefix}/academic-register')
def academic_register(
    user: CurrentTeacher,
    db: Session = Depends(get_db),
    search: str | None = None,
    academic_period: str | None = None,
    offset: int = 0,
    limit: int = 500,
) -> dict[str, Any]:
    try:
        period = selected_academic_period(db, academic_period)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    query = db.query(Student)
    if search:
        query = query.filter(Student.full_name.ilike(f'%{search}%') | Student.student_id.ilike(f'%{search}%'))
    students = query.order_by(Student.student_id).all()
    total = len(students)
    page = students[max(offset, 0):max(offset, 0) + min(max(limit, 1), 500)]
    records = subject_records_by_student(db, [student.id for student in page], period)
    subjects = db.query(Subject).filter(Subject.code.in_(SUBJECTS)).order_by(Subject.code).all()
    items = []
    for student in page:
        row = build_register_row(student, records.get(student.id, {}), period)
        current, _ = student_risk_view(student, db)
        row.update({'risk_level': current['risk_level'], 'risk_probability': current['risk_probability']})
        items.append(row)
    return {
        'subjects': [{'code': subject.code, 'name': subject.name} for subject in subjects],
        'academic_period': period,
        'academic_periods': academic_periods(db),
        'items': items,
        'total': total,
        'offset': max(offset, 0),
        'limit': min(max(limit, 1), 500),
        'risk_scope': 'global model; subject marks are academic context and are not model features',
    }


def student_subject_records(student: Student, db: Session, academic_period: str | None = None) -> dict[str, Any]:
    try:
        period = selected_academic_period(db, academic_period)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    records = subject_records_by_student(db, [student.id], period).get(student.id, {})
    subjects = db.query(Subject).filter(Subject.code.in_(SUBJECTS)).order_by(Subject.code).all()
    return {
        'student_id': student.student_id,
        'academic_period': period,
        'academic_periods': academic_periods(db),
        'subjects': {subject.code: {'name': subject.name, **serialize_record(records.get(subject.code))} for subject in subjects},
        **academic_totals(records),
        'risk_scope': 'global model; subject marks are not model features',
    }


@app.get(f'{settings.api_v1_prefix}/students/me/academic-records')
def my_academic_records(student: CurrentStudent, db: Session = Depends(get_db), academic_period: str | None = None) -> dict[str, Any]:
    return student_subject_records(student, db, academic_period)


@app.get(f'{settings.api_v1_prefix}/students/{{student_id}}/academic-records')
def get_student_academic_records(student_id: int, user: CurrentTeacher, db: Session = Depends(get_db), academic_period: str | None = None) -> dict[str, Any]:
    student = db.query(Student).filter(Student.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail='Student not found')
    return student_subject_records(student, db, academic_period)


@app.get(f'{settings.api_v1_prefix}/students/{{student_id}}/subjects/{{subject_code}}/assignments')
def student_subject_assignments(student_id: int, subject_code: str, user: CurrentTeacher, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    student = db.query(Student).filter(Student.id == student_id).first()
    subject = db.query(Subject).filter(Subject.code == subject_code.upper(), Subject.code.in_(SUBJECTS)).first()
    if student is None:
        raise HTTPException(status_code=404, detail='Student not found')
    if subject is None:
        raise HTTPException(status_code=404, detail='Subject not found')
    assignments = db.query(Assignment).filter(Assignment.subject_id == subject.id).order_by(Assignment.due_date).all()
    result = []
    for assignment in assignments:
        submission = db.query(Submission).filter_by(student_id=student.id, assignment_id=assignment.id).first()
        result.append({
            'id': assignment.id,
            'title': assignment.title,
            'subject_code': subject.code,
            'status': assignment.status,
            'due_date': assignment.due_date.isoformat() if assignment.due_date else None,
            'max_marks': assignment.max_marks,
            'submission_status': submission.status if submission else 'not_submitted',
            'uploaded': bool(submission and submission.stored_path),
            'file_name': submission.file_name if submission else None,
            'grade': submission.grade if submission else None,
            'feedback': submission.feedback if submission else None,
            'submitted_at': submission.submitted_at.isoformat() if submission and submission.submitted_at else None,
        })
    return result


@app.patch(f'{settings.api_v1_prefix}/academic-register/{{student_id}}/{{subject_code}}')
def update_academic_record(
    student_id: int,
    subject_code: str,
    payload: SubjectAcademicRecordUpdate,
    user: CurrentTeacher,
    academic_period: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    student = db.query(Student).filter(Student.id == student_id).first()
    subject = db.query(Subject).filter(Subject.code == subject_code.upper(), Subject.code.in_(SUBJECTS)).first()
    if student is None:
        raise HTTPException(status_code=404, detail='Student not found')
    if subject is None:
        raise HTTPException(status_code=404, detail='Subject not found')
    try:
        period = normalize_academic_period(academic_period)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record = db.query(StudentSubjectAcademicRecord).filter_by(student_id=student.id, subject_id=subject.id, academic_period=period).first()
    if record is None:
        record = StudentSubjectAcademicRecord(student_id=student.id, subject_id=subject.id, academic_period=period)
        db.add(record)
        db.flush()
    updates = payload.model_dump(exclude_unset=True)
    old_values = {field: getattr(record, field) for field in updates}
    for field, value in updates.items():
        setattr(record, field, value)
    record.updated_by_user_id = user.id
    db.add(StudentSubjectAcademicRecordHistory(
        academic_record_id=record.id,
        changed_by_user_id=user.id,
        change_kind='manual',
        fa1=record.fa1,
        fa1_observed_at=record.fa1_observed_at,
        fa2=record.fa2,
        fa2_observed_at=record.fa2_observed_at,
        assignment_mark=record.assignment_mark,
        assignment_observed_at=record.assignment_observed_at,
        attendance_rate=record.attendance_rate,
        attendance_observed_at=record.attendance_observed_at,
    ))
    db.add(AuditLog(
        actor_user_id=user.id,
        action='academic_subject_record.updated',
        resource_type='student_subject_academic_record',
        resource_id=f'{student.id}:{subject.code}:{period}',
        detail={'student_id': student.student_id, 'subject_code': subject.code, 'academic_period': period, 'old_values': old_values, 'new_values': updates},
    ))
    db.commit()
    db.refresh(record)
    records = subject_records_by_student(db, [student.id], period).get(student.id, {})
    register_row = build_register_row(student, records, period)
    current_student, _ = student_risk_view(student, db)
    register_row.update({'risk_level': current_student['risk_level'], 'risk_probability': current_student['risk_probability']})
    return {
        'student_id': student.student_id,
        'subject_code': subject.code,
        'academic_period': period,
        **serialize_record(record),
        'register_row': register_row,
    }


@app.get(f'{settings.api_v1_prefix}/me')
def current_profile(user: CurrentUser) -> dict[str, Any]:
    return {'id': user.id, 'email': user.email, 'name': user.full_name, 'role': user.role.upper()}


@app.get(f'{settings.api_v1_prefix}/dashboard/teacher')
def teacher_dashboard(user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    students = db.query(Student).order_by(Student.full_name).all()
    current_students = [student_risk_view(student, db)[0] for student in students]
    assignments = db.query(Assignment).filter(Assignment.status == 'active').all()
    submissions = db.query(Submission).all()
    pending_reviews = sum(item.status in {'submitted', 'late'} and item.grade is None for item in submissions)
    drafts = db.query(InterventionDraft).filter(InterventionDraft.status == 'draft').count()
    now = datetime.utcnow()
    return {
        'teacher_name': user.full_name,
        'summary': {
            'students': len(students),
            'assignments': len(assignments),
            'submissions': len(submissions),
            'pending_reviews': pending_reviews,
            'intervention_drafts': drafts,
            'high_risk': sum(item['risk_level'] == 'HIGH' for item in current_students),
            'medium_risk': sum(item['risk_level'] == 'MEDIUM' for item in current_students),
            'low_risk': sum(item['risk_level'] == 'LOW' for item in current_students),
        },
        'students_needing_attention': [item for item in current_students if item['risk_level'] in {'HIGH', 'MEDIUM'}][:12],
        'assignments': [AssignmentOut.model_validate(item).model_dump() for item in assignments[:6]],
        'upcoming_deadlines': [AssignmentOut.model_validate(item).model_dump() for item in assignments if item.due_date and item.due_date >= now][:8],
    }


@app.get(f'{settings.api_v1_prefix}/dashboard/student')
def student_dashboard(student: CurrentStudent, db: Session = Depends(get_db)) -> dict[str, Any]:
    submissions = db.query(Submission).filter(Submission.student_id == student.id).all()
    assigned_ids = select(AssignmentStudent.assignment_id).where(AssignmentStudent.student_id == student.id)
    assignments = db.query(Assignment).filter(
        (Assignment.status == 'active') & ((Assignment.id.in_(assigned_ids)) | (Assignment.section == student.section))
    ).all()
    unread = db.query(Notification).filter(Notification.user_id == student_user_id(db, student.id), Notification.read_at.is_(None)).count()
    return {
        'student': StudentSelfOut.model_validate(student).model_dump(),
        'assignments': [AssignmentOut.model_validate(item).model_dump() for item in assignments],
        'recent_submissions': [SubmissionOut.model_validate(item).model_dump() for item in submissions],
        'unread_notifications': unread,
    }


@app.get(f'{settings.api_v1_prefix}/students')
def list_students(
    user: CurrentTeacher,
    db: Session = Depends(get_db),
    search: str | None = None,
    risk: str | None = None,
    department: str | None = None,
    section: str | None = None,
    course: str | None = None,
    momentum: str | None = None,
    attendance_min: float | None = None,
    attendance_max: float | None = None,
    sort: str = 'full_name',
    direction: str = 'asc',
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    query = db.query(Student)
    if search:
        query = query.filter(Student.full_name.ilike(f'%{search}%') | Student.student_id.ilike(f'%{search}%'))
    if department:
        query = query.filter(Student.department == department)
    if section:
        query = query.filter(Student.section == section)
    if course:
        query = query.filter(Student.course.has(Course.code == course))
    response_items = []
    for student in query.all():
        values, _ = student_risk_view(student, db)
        if attendance_min is not None and values['attendance'] < attendance_min:
            continue
        if attendance_max is not None and values['attendance'] > attendance_max:
            continue
        if risk and values['risk_level'] != risk.upper():
            continue
        observations = db.query(AcademicMomentum.value).filter(AcademicMomentum.student_id == student.id, AcademicMomentum.metric == 'assessment').order_by(AcademicMomentum.observed_at).all()
        values['momentum_trend'] = calculate_momentum([row[0] for row in observations])['classification']
        if momentum and values['momentum_trend'] != momentum.upper():
            continue
        response_items.append(values)
    sortable = {'full_name', 'risk_level', 'risk_probability', 'attendance', 'current_gpa'}
    sort_key = sort if sort in sortable else 'full_name'
    response_items.sort(key=lambda item: item[sort_key], reverse=direction.lower() == 'desc')
    total = len(response_items)
    items = response_items[max(offset, 0):max(offset, 0) + min(max(limit, 1), 100)]
    return {'items': items, 'total': total}


@app.get(f'{settings.api_v1_prefix}/students/me')
def my_student_profile(student: CurrentStudent) -> StudentSelfOut:
    return StudentSelfOut.model_validate(student)


@app.get(f'{settings.api_v1_prefix}/students/me/momentum')
def my_student_momentum(student: CurrentStudent, db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.query(AcademicMomentum).filter(AcademicMomentum.student_id == student.id).order_by(AcademicMomentum.observed_at).all()
    grouped: dict[str, list[AcademicMomentum]] = {}
    for row in rows:
        grouped.setdefault(row.metric, []).append(row)
    return {'metrics': {metric: {'classification': calculate_momentum([item.value for item in history])['classification'], 'observations': [{'value': item.value, 'observed_at': item.observed_at.isoformat()} for item in history]} for metric, history in grouped.items()}}


@app.get(f'{settings.api_v1_prefix}/subjects/me')
def my_subjects(student: CurrentStudent, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    if student.course_id is None:
        return []
    course = student.course
    subject = db.query(Subject).filter(Subject.id == course.subject_id).first() if course and course.subject_id else None
    assessments = db.query(Assessment).filter(Assessment.course_id == course.id).all() if course else []
    results = []
    for assessment in assessments:
        mark = db.query(Mark).filter(Mark.student_id == student.id, Mark.assessment_id == assessment.id).order_by(Mark.recorded_at.desc()).first()
        results.append({'assessment': assessment.title, 'score': mark.score if mark else None, 'maximum': assessment.maximum_marks, 'recorded_at': mark.recorded_at.isoformat() if mark else None})
    attendance_rows = db.query(Attendance).filter(Attendance.student_id == student.id, Attendance.course_id == course.id).all() if course else []
    recorded_rates = [item.attendance_rate for item in attendance_rows if item.attendance_rate is not None]
    attendance_rate = sum(recorded_rates) / len(recorded_rates) if recorded_rates else sum(item.attended for item in attendance_rows) / len(attendance_rows) * 100 if attendance_rows else None
    teacher_name = course.teacher.user.full_name if course and course.teacher and course.teacher.user else None
    return [{'course': course.name, 'course_code': course.code, 'section': course.section, 'subject': subject.name if subject else course.name, 'teacher': teacher_name, 'attendance': attendance_rate, 'assessments': results}]


@app.get(f'{settings.api_v1_prefix}/support/resources')
def student_support_resources(student: CurrentStudent, query: str = 'academic support study planning mentoring') -> dict[str, Any]:
    result = retrieve(query)
    return {'student_id': student.student_id, **result}


def _student_access(student_id: int, user: CurrentUser, db: Session) -> Student:
    student = db.query(Student).filter(Student.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail='Student not found')
    if user.role.upper() == 'STUDENT' and student.user_id != user.id:
        raise HTTPException(status_code=404, detail='Student not found')
    if user.role.upper() not in {'TEACHER', 'STUDENT'}:
        raise HTTPException(status_code=403, detail='Student access required')
    return student


def _build_support_recommendations(prediction: dict[str, Any], explanation: dict[str, Any]) -> list[dict[str, Any]]:
    risk_level = str(prediction.get('risk_level', 'LOW')).upper()
    contributions = explanation.get('contributions', {}) if isinstance(explanation, dict) else {}
    ranked = sorted(contributions.items(), key=lambda item: abs(float(item[1]) if isinstance(item[1], (int, float)) else 0.0), reverse=True)
    top_factor = ranked[0][0] if ranked else 'academic_progress'
    if risk_level == 'HIGH':
        return [
            {'title': 'Faculty check-in and support plan', 'action_type': 'FACULTY_CHECK_IN', 'priority': 'high', 'rationale': f'Highest risk signal is {top_factor} and needs a structured academic review.'},
            {'title': 'Attendance recovery plan', 'action_type': 'ATTENDANCE_REVIEW', 'priority': 'high', 'rationale': 'Review attendance barriers and create a recovery plan with missed learning targets.'},
            {'title': 'Assessment and deadline recovery', 'action_type': 'ASSESSMENT_RECOVERY', 'priority': 'medium', 'rationale': 'Assist with deadlines and assessment planning to stabilize academic momentum.'},
        ]
    if risk_level == 'MEDIUM':
        return [
            {'title': 'Targeted academic mentoring', 'action_type': 'MENTORING', 'priority': 'medium', 'rationale': f'Current risk is moderated by {top_factor}; a concise coaching plan will help reduce the trend.'},
            {'title': 'Engagement and resource check', 'action_type': 'RESOURCE_SUPPORT', 'priority': 'medium', 'rationale': 'Check whether study resources, assignments, and attendance support are sufficient.'},
        ]
    return [
        {'title': 'Maintain positive momentum', 'action_type': 'SUCCESS_MAINTENANCE', 'priority': 'low', 'rationale': 'Continue the current direction while monitoring for shifts in attendance or assessment performance.'},
    ]


@app.get(f'{settings.api_v1_prefix}/students/{{student_id}}/support-profile')
def student_support_profile(student_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> dict[str, Any]:
    student = _student_access(student_id, user, db)
    features = student_features(student, db)
    prediction = predict_with_active_model(features, db)
    explanation = explain_with_active_model(features, db, target_class=prediction['risk_level'])
    evidence = [
        {'feature': name, 'impact': float(value), 'direction': 'positive' if float(value) > 0 else 'negative'}
        for name, value in sorted(explanation.get('contributions', {}).items(), key=lambda item: abs(float(item[1]) if isinstance(item[1], (int, float)) else 0.0), reverse=True)
    ]
    actions = db.query(SupportAction).filter(SupportAction.student_id == student.id).order_by(SupportAction.created_at.desc()).all()
    follow_ups = db.query(SupportFollowUp).filter(SupportFollowUp.student_id == student.id).order_by(SupportFollowUp.scheduled_date.desc(), SupportFollowUp.id.desc()).all()
    versions = db.query(SupportPlanVersion).filter(SupportPlanVersion.student_id == student.id).order_by(SupportPlanVersion.version.desc(), SupportPlanVersion.created_at.desc()).all()
    student_data, _ = student_risk_view(student, db)
    return {
        'student': {**student_data, 'id': student.id, 'student_id': student.student_id},
        'risk': {'level': prediction['risk_level'], 'probability': prediction['risk_probability'], 'class_probabilities': prediction.get('class_probabilities', {})},
        'risk_evidence': evidence,
        'recommended_actions': _build_support_recommendations(prediction, explanation),
        'support_actions': [
            {
                'id': item.id,
                'student_id': item.student_id,
                'title': item.title,
                'action_type': item.action_type,
                'status': normalize_support_status(item.status, default='PENDING_FACULTY_REVIEW'),
                'due_date': item.due_date.isoformat() if item.due_date else None,
                'notes': item.notes,
                'outcome': item.outcome,
                'completed_at': item.completed_at.isoformat() if item.completed_at else None,
            }
            for item in actions
        ],
        'follow_ups': [
            {
                'id': item.id,
                'student_id': item.student_id,
                'assigned_to': item.assigned_to,
                'scheduled_date': item.scheduled_date.isoformat() if item.scheduled_date else None,
                'status': normalize_support_status(item.status, default='SCHEDULED'),
                'notes': item.notes,
                'outcome': item.outcome,
                'completed_at': item.completed_at.isoformat() if item.completed_at else None,
            }
            for item in follow_ups
        ],
        'support_plan_versions': [
            {
                'id': item.id,
                'version': item.version,
                'summary': item.summary,
                'plan_json': item.plan_json,
                'created_at': item.created_at.isoformat(),
            }
            for item in versions
        ],
    }


@app.get(f'{settings.api_v1_prefix}/students/{{student_id}}/support-plan')
def student_support_plan(student_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> dict[str, Any]:
    profile = student_support_profile(student_id, user, db)
    versions = profile.get('support_plan_versions') or []
    latest = versions[0] if versions else None
    return {
        'student_id': student_id,
        'risk_level': profile['risk']['level'],
        'plan': profile['recommended_actions'],
        'latest_version': latest,
        'version_history': versions,
    }


@app.post(f'{settings.api_v1_prefix}/students/{{student_id}}/support-plan')
def create_student_support_plan(student_id: int, user: CurrentUser, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    student = _student_access(student_id, user, db)
    if user.role.upper() != 'TEACHER':
        raise HTTPException(status_code=403, detail='Only teachers can create support plans for students.')
    plan = payload.get('plan') or payload.get('recommendations') or student_support_profile(student_id, user, db)['recommended_actions']
    summary = str(payload.get('summary') or 'Support plan updated for review.')
    current_revision = db.query(SupportPlanVersion).filter(SupportPlanVersion.student_id == student.id).order_by(SupportPlanVersion.version.desc()).first()
    version = (current_revision.version if current_revision else 0) + 1
    record = SupportPlanVersion(student_id=student.id, teacher_id=user.id, version=version, summary=summary, plan_json={'plan': plan})
    db.add(record)
    db.commit()
    db.refresh(record)
    return {'id': record.id, 'student_id': student.id, 'version': record.version, 'summary': record.summary, 'plan': record.plan_json.get('plan', plan), 'created_at': record.created_at.isoformat()}


@app.get(f'{settings.api_v1_prefix}/students/{{student_id}}/support-plan/history')
def student_support_plan_history(student_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> dict[str, Any]:
    student = _student_access(student_id, user, db)
    items = db.query(SupportPlanVersion).filter(SupportPlanVersion.student_id == student.id).order_by(SupportPlanVersion.version.desc(), SupportPlanVersion.created_at.desc()).all()
    return {'student_id': student.id, 'items': [{'id': item.id, 'version': item.version, 'summary': item.summary, 'plan': item.plan_json.get('plan', []), 'created_at': item.created_at.isoformat()} for item in items]}


@app.get(f'{settings.api_v1_prefix}/students/{{student_id}}/support-timeline')
def student_support_timeline(student_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> dict[str, Any]:
    student = _student_access(student_id, user, db)
    risk_history = db.query(RiskSnapshot).filter(RiskSnapshot.student_id == student.id).order_by(RiskSnapshot.recorded_at.desc()).all()
    actions = db.query(SupportAction).filter(SupportAction.student_id == student.id).order_by(SupportAction.created_at.desc()).all()
    follow_ups = db.query(SupportFollowUp).filter(SupportFollowUp.student_id == student.id).order_by(SupportFollowUp.scheduled_date.desc(), SupportFollowUp.id.desc()).all()
    plan_versions = db.query(SupportPlanVersion).filter(SupportPlanVersion.student_id == student.id).order_by(SupportPlanVersion.version.desc(), SupportPlanVersion.created_at.desc()).all()
    events = []
    for item in risk_history:
        events.append({'kind': 'risk_snapshot', 'occurred_at': item.recorded_at.isoformat(), 'title': f'Risk snapshot: {item.risk_level}', 'summary': f'Probability {item.probability}', 'status': item.risk_level})
    for item in actions:
        occurred_at = (item.completed_at or item.due_date or item.created_at).isoformat() if item.completed_at or item.due_date or item.created_at else None
        events.append({'kind': 'support_action', 'occurred_at': occurred_at, 'title': item.title, 'summary': item.action_type, 'status': normalize_support_status(item.status, default='PENDING_FACULTY_REVIEW')})
    for item in follow_ups:
        occurred_at = (item.completed_at or item.scheduled_date or item.created_at).isoformat() if item.completed_at or item.scheduled_date or item.created_at else None
        events.append({'kind': 'follow_up', 'occurred_at': occurred_at, 'title': 'Follow-up scheduled', 'summary': item.notes or item.assigned_to, 'status': normalize_support_status(item.status, default='SCHEDULED')})
    for item in plan_versions:
        events.append({'kind': 'support_plan_version', 'occurred_at': item.created_at.isoformat(), 'title': f'Support plan v{item.version}', 'summary': item.summary or 'Support plan updated', 'status': 'UPDATED'})
    events.sort(key=lambda item: item['occurred_at'] or '1970-01-01T00:00:00', reverse=True)
    return {'student_id': student.id, 'items': events}


@app.get(f'{settings.api_v1_prefix}/students/{{student_id}}/support-actions')
def list_student_support_actions(student_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> dict[str, Any]:
    student = _student_access(student_id, user, db)
    items = db.query(SupportAction).filter(SupportAction.student_id == student.id).order_by(SupportAction.created_at.desc()).all()
    return {'items': [{
        'id': item.id,
        'student_id': item.student_id,
        'title': item.title,
        'action_type': item.action_type,
        'status': normalize_support_status(item.status, default='PENDING_FACULTY_REVIEW'),
        'due_date': item.due_date.isoformat() if item.due_date else None,
        'notes': item.notes,
        'evidence': item.evidence,
        'outcome': item.outcome,
        'completed_at': item.completed_at.isoformat() if item.completed_at else None,
    } for item in items]}


@app.get(f'{settings.api_v1_prefix}/students/{{student_id}}/support-effectiveness')
def student_support_effectiveness(student_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> dict[str, Any]:
    student = _student_access(student_id, user, db)
    snapshots = db.query(RiskSnapshot).filter(RiskSnapshot.student_id == student.id).order_by(RiskSnapshot.recorded_at.asc()).all()
    latest = snapshots[-1] if snapshots else None
    baseline = snapshots[0] if len(snapshots) > 1 else snapshots[0] if snapshots else None
    support_actions = db.query(SupportAction).filter(SupportAction.student_id == student.id).order_by(SupportAction.created_at.asc()).all()
    latest_completed = next((item for item in reversed(support_actions) if item.completed_at), None)
    baseline_prob = baseline.probability if baseline else student.risk_probability
    latest_prob = latest.probability if latest else student.risk_probability
    delta = latest_prob - baseline_prob if baseline is not None else 0.0
    outcome_summary = {
        'baseline_risk_probability': float(baseline_prob),
        'latest_risk_probability': float(latest_prob),
        'change_in_risk_probability': float(delta),
        'support_actions_completed': sum(1 for item in support_actions if normalize_support_status(item.status) == 'COMPLETED'),
        'latest_completed_action': {'id': latest_completed.id, 'title': latest_completed.title} if latest_completed else None,
        'observed_after_intervention': 'Observed change after the support plan and follow-up workflow.' if latest_completed else 'No completed support action has been recorded yet.',
    }
    return {'student_id': student.id, 'summary': outcome_summary, 'baseline': baseline.probability if baseline else None, 'current': latest.probability if latest else None, 'risk_probability_delta': delta}


@app.patch(f'{settings.api_v1_prefix}/support-actions/{{action_id}}')
def update_student_support_action(action_id: int, user: CurrentUser, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    action = db.query(SupportAction).filter(SupportAction.id == action_id).first()
    if action is None:
        raise HTTPException(status_code=404, detail='Support action not found')
    if user.role.upper() != 'TEACHER':
        raise HTTPException(status_code=403, detail='Only teachers can update support actions.')
    status = normalize_support_status(payload.get('status') or payload.get('state') or action.status, default='PENDING_FACULTY_REVIEW')
    action.status = status
    if payload.get('outcome') is not None:
        action.outcome = str(payload['outcome'])
    if status == 'COMPLETED' and not action.completed_at:
        action.completed_at = datetime.utcnow()
    if status in {'CANCELLED', 'MISSED'}:
        action.completed_at = action.completed_at or datetime.utcnow()
    notes = payload.get('notes')
    if notes is not None:
        action.notes = str(notes)
    db.commit()
    db.refresh(action)
    return {'id': action.id, 'status': action.status, 'outcome': action.outcome, 'completed_at': action.completed_at.isoformat() if action.completed_at else None}


@app.patch(f'{settings.api_v1_prefix}/support-follow-ups/{{follow_up_id}}')
def update_student_follow_up(follow_up_id: int, user: CurrentUser, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.query(SupportFollowUp).filter(SupportFollowUp.id == follow_up_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail='Follow-up not found')
    action = str(payload.get('action') or payload.get('status') or item.status).strip().lower()
    status = item.status
    if action in {'reschedule', 'rescheduled'}:
        status = 'SCHEDULED'
        scheduled = payload.get('scheduled_date') or payload.get('date')
        parsed = coerce_datetime(scheduled)
        if parsed:
            item.scheduled_date = parsed
    elif action in {'complete', 'completed'}:
        status = 'COMPLETED'
        item.completed_at = item.completed_at or datetime.utcnow()
    elif action in {'cancel', 'cancelled', 'canceled'}:
        status = 'CANCELLED'
        item.completed_at = item.completed_at or datetime.utcnow()
    elif action in {'miss', 'missed'}:
        status = 'MISSED'
        item.completed_at = item.completed_at or datetime.utcnow()
    elif action in {'schedule', 'scheduled'}:
        status = 'SCHEDULED'
    elif payload.get('status') is not None:
        status = normalize_support_status(payload['status'], default='SCHEDULED')
    item.status = normalize_support_status(status, default='SCHEDULED')
    if payload.get('outcome') is not None:
        item.outcome = str(payload['outcome'])
    if payload.get('notes') is not None:
        item.notes = str(payload['notes'])
    db.commit()
    db.refresh(item)
    return {'id': item.id, 'status': item.status, 'scheduled_date': item.scheduled_date.isoformat() if item.scheduled_date else None, 'outcome': item.outcome, 'completed_at': item.completed_at.isoformat() if item.completed_at else None}


@app.post(f'{settings.api_v1_prefix}/students/{{student_id}}/support-actions')
def create_student_support_action(student_id: int, user: CurrentUser, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    student = _student_access(student_id, user, db)
    if user.role.upper() != 'TEACHER':
        raise HTTPException(status_code=403, detail='Only teachers can create or assign support actions.')
    title = str(payload.get('title') or 'Support action')
    action_type = str(payload.get('action_type') or 'GENERAL_SUPPORT').upper()
    due_date = payload.get('due_date')
    parsed_due_date = None
    if due_date:
        if isinstance(due_date, str):
            parsed_due_date = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
        elif isinstance(due_date, datetime):
            parsed_due_date = due_date
    student_features_payload = student_features(student, db)
    risk_prediction = predict_with_active_model(student_features_payload, db)
    action = SupportAction(
        student_id=student.id,
        teacher_id=user.id,
        title=title,
        action_type=action_type,
        status='PENDING_FACULTY_REVIEW',
        due_date=parsed_due_date,
        evidence={
            'risk_level': risk_prediction['risk_level'],
            'risk_probability': risk_prediction['risk_probability'],
            'source': 'student_support_profile',
        },
        notes=str(payload.get('notes') or '')
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return JSONResponse(
        content={
            'id': action.id,
            'student_id': action.student_id,
            'title': action.title,
            'action_type': action.action_type,
            'status': action.status,
            'due_date': action.due_date.isoformat() if action.due_date else None,
            'notes': action.notes,
            'evidence': action.evidence,
        },
        status_code=201,
    )


@app.post(f'{settings.api_v1_prefix}/interventions/{{student_id}}/follow-up')
def create_student_follow_up(student_id: int, user: CurrentUser, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    student = _student_access(student_id, user, db)
    if user.role.upper() != 'TEACHER':
        raise HTTPException(status_code=403, detail='Only teachers can schedule follow-up checks.')
    scheduled = payload.get('scheduled_date')
    parsed_scheduled = None
    if scheduled:
        if isinstance(scheduled, str):
            parsed_scheduled = datetime.fromisoformat(scheduled.replace('Z', '+00:00'))
        elif isinstance(scheduled, datetime):
            parsed_scheduled = scheduled
    follow_up = SupportFollowUp(
        student_id=student.id,
        assigned_to=str(payload.get('assigned_to') or user.email),
        scheduled_date=parsed_scheduled,
        notes=str(payload.get('notes') or ''),
        status='SCHEDULED',
        outcome=None,
    )
    db.add(follow_up)
    db.commit()
    db.refresh(follow_up)
    return {
        'id': follow_up.id,
        'student_id': student.id,
        'assigned_to': follow_up.assigned_to,
        'scheduled_date': follow_up.scheduled_date.isoformat() if follow_up.scheduled_date else None,
        'status': follow_up.status,
        'notes': follow_up.notes,
    }


@app.get(f'{settings.api_v1_prefix}/students/{{student_id}}')
def get_student(student_id: str, user: CurrentUser, db: Session = Depends(get_db)) -> dict[str, Any]:
    query = db.query(Student)
    if student_id.isdigit():
        query = query.filter(Student.id == int(student_id))
    else:
        query = query.filter(Student.student_id == student_id)
    student = query.first()
    if student is None:
        raise HTTPException(status_code=404, detail='Student not found')
    if user.role.upper() == 'STUDENT':
        if student.user_id != user.id:
            raise HTTPException(status_code=404, detail='Student not found')
        return {'student': StudentSelfOut.model_validate(student).model_dump()}
    if user.role.upper() != 'TEACHER':
        raise HTTPException(status_code=403, detail='Student access required')
    student_data, _ = student_risk_view(student, db)
    observations = db.query(AcademicMomentum).filter(AcademicMomentum.student_id == student.id).order_by(AcademicMomentum.observed_at).all()
    submissions = db.query(Submission).filter(Submission.student_id == student.id).all()
    snapshots = db.query(RiskSnapshot).filter(RiskSnapshot.student_id == student.id).order_by(RiskSnapshot.recorded_at).all()
    return {
        'student': student_data,
        'momentum': [{'metric': item.metric, 'value': item.value, 'observed_at': item.observed_at.isoformat()} for item in observations],
        'submissions': [SubmissionOut.model_validate(item).model_dump() for item in submissions],
        'risk_history': [{'risk_level': item.risk_level, 'recorded_at': item.recorded_at.isoformat()} for item in snapshots],
        'academic_records': student_subject_records(student, db),
    }


@app.get(f'{settings.api_v1_prefix}/students/{{student_id}}/risk')
def current_student_risk(student_id: int, user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    student = db.query(Student).filter(Student.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail='Student not found')
    features = student_features(student, db)
    try:
        prediction = predict_with_active_model(features, db)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail='The production risk model is unavailable.') from exc
    return {
        'student': {'id': student.id, 'student_id': student.student_id, 'full_name': student.full_name},
        'features': features,
        'prediction': prediction,
    }


@app.get(f'{settings.api_v1_prefix}/students/{{student_id}}/momentum')
def student_momentum(student_id: int, user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    student = db.query(Student).filter(Student.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail='Student not found')
    observations = db.query(AcademicMomentum).filter(AcademicMomentum.student_id == student.id).order_by(AcademicMomentum.observed_at).all()
    grouped: dict[str, list[Any]] = {}
    for item in observations:
        grouped.setdefault(item.metric, []).append(item)
    metrics = {}
    for metric, items in grouped.items():
        result = calculate_momentum([item.value for item in items])
        result['observations'] = [{'value': item.value, 'observed_at': item.observed_at.isoformat()} for item in items]
        metrics[metric] = result
    return {'student_id': student.student_id, 'metrics': metrics}


@app.get(f'{settings.api_v1_prefix}/students/{{student_id}}/explanation')
def student_explanation(student_id: int, user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    student = db.query(Student).filter(Student.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail='Student not found')
    features = student_features(student, db)
    try:
        prediction = predict_with_active_model(features, db)
        explanation = explain_with_active_model(features, db, target_class=prediction['risk_level'])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail='Risk model or SHAP background is unavailable.') from exc
    return {
        'student': {'id': student.id, 'student_id': student.student_id, 'full_name': student.full_name},
        'prediction': prediction,
        'features': features,
        'explanation': explanation,
    }


@app.get(f'{settings.api_v1_prefix}/students/{{student_id}}/shap')
def student_shap(student_id: int, user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    student = db.query(Student).filter(Student.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail='Student not found')
    features = student_features(student, db)
    try:
        prediction = predict_with_active_model(features, db)
        explanation = explain_with_active_model(features, db, target_class=prediction['risk_level'])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail='Risk model is not trained. Run the documented training command first.') from exc
    record = RiskPrediction(student_id=student.id, risk_level=prediction['risk_level'], probability=prediction['risk_probability'], model_version=prediction['model_version'], prediction_timestamp=prediction['prediction_timestamp'], input_features=features)
    db.add(record)
    db.flush()
    from backend.app.models import ShapExplanation

    db.add(ShapExplanation(prediction_id=record.id, values=explanation['contributions'], base_value=explanation['base_value'], model_version=explanation['model_version']))
    student.risk_level = prediction['risk_level']
    student.risk_probability = prediction['risk_probability']
    db.add(RiskSnapshot(student_id=student.id, risk_level=prediction['risk_level'], probability=prediction['risk_probability'], recorded_at=prediction['prediction_timestamp'].replace(tzinfo=None)))
    db.commit()
    return {'prediction': prediction, 'explanation': explanation, 'question': 'Why is this student at risk?'}


@app.post(f'{settings.api_v1_prefix}/risk/predict')
def risk_prediction(payload: RiskFeatureInput, user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        result = predict_with_active_model(payload.feature_dict(), db)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail='Risk model is not trained. Run the documented training command first.') from exc
    if payload.student_id is not None:
        student = db.query(Student).filter(Student.id == payload.student_id).first()
        if student is None:
            raise HTTPException(status_code=404, detail='Student not found')
        student.risk_level = result['risk_level']
        student.risk_probability = result['risk_probability']
        db.add(RiskPrediction(student_id=student.id, risk_level=result['risk_level'], probability=result['risk_probability'], model_version=result['model_version'], prediction_timestamp=result['prediction_timestamp'], input_features=payload.feature_dict()))
        db.add(RiskSnapshot(student_id=student.id, risk_level=result['risk_level'], probability=result['risk_probability'], recorded_at=result['prediction_timestamp'].replace(tzinfo=None)))
        db.commit()
    return result


@app.get(f'{settings.api_v1_prefix}/models/registry')
def list_model_registry(user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    entries = db.query(ModelRegistryEntry).order_by(ModelRegistryEntry.created_at.desc()).all()
    return {
        'current_production_model': production_model_registry_entry(),
        'history': [{
            'id': entry.id,
            'model_id': entry.model_id,
            'model_version': entry.model_version,
            'model_type': entry.model_type,
            'feature_contract_version': entry.feature_contract_version,
            'feature_contract': entry.feature_schema,
            'training_period': entry.training_period,
            'training_dataset_version': entry.training_dataset_version,
            'training_dataset_hash': entry.training_dataset_hash,
            'training_timestamp': entry.training_timestamp.isoformat() if entry.training_timestamp else None,
            'validation_metrics': entry.validation_metrics,
            'artifact_identifier': entry.artifact_identifier,
            'artifact_hash': entry.artifact_hash,
            'status': entry.status,
            'deployment_status': entry.deployment_status,
            'notes': entry.notes,
            'created_at': entry.created_at.isoformat(),
            'created_by_user_id': entry.created_by_user_id,
            'dataset_id': entry.dataset_id,
            'dataset_version': entry.dataset_version,
            'dataset_fingerprint': entry.dataset_fingerprint,
            'target_definition': entry.target_definition,
            'aggregation_strategy': entry.aggregation_strategy,
            'training_periods': entry.training_periods,
            'validation_periods': entry.validation_periods,
            'test_periods': entry.test_periods,
            'algorithm': entry.algorithm,
            'hyperparameters': entry.hyperparameters,
            'random_seed': entry.random_seed,
            'validation_status': entry.validation_status,
            'approval_status': entry.approval_status,
            'approved_by_user_id': entry.approved_by_user_id,
            'approved_at': entry.approved_at.isoformat() if entry.approved_at else None,
            'previous_production_model_version': entry.previous_production_model_version,
            'promoted_at': entry.promoted_at.isoformat() if entry.promoted_at else None,
            'retired_at': entry.retired_at.isoformat() if entry.retired_at else None,
            'rejected_by_user_id': entry.rejected_by_user_id,
            'rejected_at': entry.rejected_at.isoformat() if entry.rejected_at else None,
            'rejection_reason': entry.rejection_reason,
        } for entry in entries],
    }


@app.post(f'{settings.api_v1_prefix}/models/registry', status_code=201)
def create_model_registry_entry(payload: ModelRegistryEntryInput, user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    current_production = production_model_registry_entry()
    if payload.model_version == current_production['model_version']:
        raise HTTPException(status_code=409, detail='The current production model is already represented by the live artifact.')
    if db.query(ModelRegistryEntry.id).filter(ModelRegistryEntry.model_version == payload.model_version).first():
        raise HTTPException(status_code=409, detail='A registry entry with this model version already exists.')
    if any((payload.training_dataset_hash, payload.training_timestamp, payload.validation_metrics, payload.artifact_identifier, payload.artifact_hash)):
        raise HTTPException(status_code=422, detail='Training, artifact, and evaluation metadata must be produced by the Phase 3 pipeline, not supplied by a registry request.')
    entry = ModelRegistryEntry(
        model_id=payload.model_version,
        model_version=payload.model_version,
        model_type=payload.model_type,
        feature_schema=payload.feature_schema,
        feature_contract_version=payload.feature_contract_version,
        training_period=payload.training_period,
        training_dataset_version=payload.training_dataset_version,
        training_dataset_hash=payload.training_dataset_hash,
        training_timestamp=payload.training_timestamp,
        validation_metrics=payload.validation_metrics,
        artifact_identifier=payload.artifact_identifier,
        artifact_hash=payload.artifact_hash,
        notes=payload.notes,
        metrics=payload.validation_metrics,
        status=payload.status,
        deployment_status='SHADOW',
        created_by_user_id=user.id,
        validation_status='not_run',
        approval_status='not_approved',
    )
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='A registry entry with this model version already exists.') from None
    db.refresh(entry)
    phase3_audit(db, user, 'model.candidate.registered', result='candidate_metadata_only', model_version=entry.model_version, resource_id=entry.id, new_state={'status': entry.status, 'validation_status': entry.validation_status, 'approval_status': entry.approval_status, 'deployment_status': entry.deployment_status})
    return {
        'id': entry.id,
        'model_id': entry.model_id,
        'model_version': entry.model_version,
        'model_type': entry.model_type,
        'feature_contract_version': entry.feature_contract_version,
        'feature_contract': entry.feature_schema,
        'training_period': entry.training_period,
        'training_dataset_version': entry.training_dataset_version,
        'training_dataset_hash': entry.training_dataset_hash,
        'training_timestamp': entry.training_timestamp.isoformat() if entry.training_timestamp else None,
        'validation_metrics': entry.validation_metrics,
        'artifact_identifier': entry.artifact_identifier,
        'artifact_hash': entry.artifact_hash,
        'status': entry.status,
        'notes': entry.notes,
        'created_at': entry.created_at.isoformat(),
        'created_by_user_id': entry.created_by_user_id,
        'validation_status': entry.validation_status,
        'approval_status': entry.approval_status,
    }


@app.post(f'{settings.api_v1_prefix}/risk/simulate')
def risk_simulation(payload: RiskSimulationInput, user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    student = db.query(Student).filter(Student.id == payload.student_id).first() if payload.student_id is not None else None
    if student is None and payload.student_id is not None:
        raise HTTPException(status_code=404, detail='Student not found')
    if student is None:
        raise HTTPException(status_code=422, detail='A valid student_id is required for the simulation.')
    return simulate_student_risk(student, db, payload.scenario)


@app.get(f'{settings.api_v1_prefix}/risk/data-quality')
def risk_data_quality(user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    return compute_data_quality_report(db)


@app.get(f'{settings.api_v1_prefix}/risk/transitions')
def risk_transitions(user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    return risk_transition_report(db)


def phase3_policy_payload(policy: Phase3PolicyApproval | None) -> dict[str, Any]:
    if policy is None:
        return {'status': 'unapproved', 'approved_policy': None}
    return {
        'status': 'approved',
        'approved_policy': {
            'id': policy.id,
            'aggregation_strategy': policy.aggregation_strategy,
            'feature_contract': policy.feature_contract,
            'approved_by_user_id': policy.approved_by_user_id,
            'approved_at': policy.approved_at.isoformat(),
            'approval_note': policy.approval_note,
        },
    }


@app.get(f'{settings.api_v1_prefix}/ml/phase3/policy')
def phase3_policy(user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    policy = db.query(Phase3PolicyApproval).order_by(Phase3PolicyApproval.id.desc()).first()
    return {
        **phase3_policy_payload(policy),
        'supported_aggregation_strategies': ['equal_subject_mean'],
        'supported_feature_contract': ['fa1_mean', 'fa2_mean', 'assignment_mean', 'attendance_mean'],
        'note': 'Methodology approval is separate from data readiness and never creates candidate data or candidate models.',
    }


@app.post(f'{settings.api_v1_prefix}/ml/phase3/policy/approve')
def approve_phase3_policy(
    payload: Phase3PolicyApprovalRequest,
    user: CurrentTeacher,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not payload.explicit_approval:
        raise HTTPException(status_code=422, detail='Explicit faculty approval is required for the Phase 3 policy.')
    if len(payload.feature_contract) != len(set(payload.feature_contract)):
        raise HTTPException(status_code=422, detail='The approved feature contract cannot contain duplicate features.')
    previous = db.query(Phase3PolicyApproval).order_by(Phase3PolicyApproval.id.desc()).first()
    previous_state = {
        'aggregation_strategy': previous.aggregation_strategy,
        'feature_contract': previous.feature_contract,
        'approved_by_user_id': previous.approved_by_user_id,
    } if previous else {'status': 'unapproved'}
    approval = Phase3PolicyApproval(
        aggregation_strategy=payload.aggregation_strategy,
        feature_contract=payload.feature_contract,
        approved_by_user_id=user.id,
        approved_at=datetime.utcnow(),
        approval_note=payload.approval_note,
    )
    db.add(approval)
    db.flush()
    new_state = {
        'aggregation_strategy': approval.aggregation_strategy,
        'feature_contract': approval.feature_contract,
        'approved_by_user_id': approval.approved_by_user_id,
    }
    phase3_audit(
        db, user, 'phase3.policy.approved', result='approved',
        reason=payload.approval_note, resource_id=approval.id,
        previous_state=previous_state, new_state=new_state,
    )
    return {'status': 'approved', 'approved_policy': phase3_policy_payload(approval)['approved_policy']}


@app.get(f'{settings.api_v1_prefix}/ml/phase3/readiness')
def phase3_readiness(user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    dataset = build_phase3_dataset(db)
    phase3_audit(
        db, user, 'phase3.validation.checked', result='ready' if dataset['readiness']['training_ready'] else 'blocked',
        reason='; '.join(dataset['readiness']['blockers']), dataset_id=dataset['dataset_id'],
        dataset_version=dataset['dataset_version'], dataset_fingerprint=dataset['dataset_fingerprint'],
    )
    return phase3_public_report(dataset)


@app.get(f'{settings.api_v1_prefix}/ml/phase3/coverage')
def phase3_coverage(user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    dataset = build_phase3_dataset(db)
    phase3_audit(
        db, user, 'phase3.validation.coverage_viewed', result='measured', dataset_id=dataset['dataset_id'],
        dataset_version=dataset['dataset_version'], dataset_fingerprint=dataset['dataset_fingerprint'],
    )
    return {
        'dataset_id': dataset['dataset_id'],
        'dataset_version': dataset['dataset_version'],
        'dataset_fingerprint': dataset['dataset_fingerprint'],
        'created_at': dataset['created_at'],
        'counts': dataset['counts'],
        'coverage': dataset['coverage'],
        'readiness': dataset['readiness'],
        'rejected_rows': dataset['rejected_rows'],
        'duplicate_import_rows': dataset['duplicate_import_rows'],
    }


@app.get(f'{settings.api_v1_prefix}/ml/phase3/dataset')
def phase3_dataset_export(
    user: CurrentTeacher,
    db: Session = Depends(get_db),
    aggregation_strategy: str | None = None,
    feature_contract: list[str] | None = Query(None),
) -> StreamingResponse:
    dataset = build_phase3_dataset(db, aggregation_strategy=aggregation_strategy, feature_contract=feature_contract)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=PHASE3_DATASET_FIELDS)
    writer.writeheader()
    export_rows = dataset['candidate_rows'] if aggregation_strategy and feature_contract else dataset['rows']
    for row in export_rows:
        values = dict(row)
        for name in ('exclusion_reasons', 'source_record_ids', 'source_subjects', 'source_batch_ids', 'source_filenames', 'source_checksums'):
            if name in values:
                values[name] = json.dumps(values[name], separators=(',', ':'))
        writer.writerow(values)
    phase3_audit(
        db, user, 'phase3.dataset.generated', result='aggregate_candidate_dataset_exported' if aggregation_strategy and feature_contract else 'source_observation_dataset_exported', dataset_id=dataset['dataset_id'],
        dataset_version=dataset['dataset_version'], dataset_fingerprint=dataset['dataset_fingerprint'],
    )
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type='text/csv',
        headers={
            'Content-Disposition': 'attachment; filename="phase3-candidate-dataset.csv"',
            'X-Dataset-Id': dataset['dataset_id'],
            'X-Dataset-Version': dataset['dataset_version'],
            'X-Dataset-Fingerprint': dataset['dataset_fingerprint'],
            'X-Training-Eligible': str(dataset['training_eligible']).lower(),
        },
    )


def candidate_registry_payload(entry: ModelRegistryEntry) -> dict[str, Any]:
    return {
        'id': entry.id,
        'model_version': entry.model_version,
        'status': entry.status,
        'model_type': entry.model_type,
        'feature_contract': entry.feature_schema,
        'feature_contract_version': entry.feature_contract_version,
        'dataset_id': entry.dataset_id,
        'dataset_version': entry.dataset_version,
        'dataset_fingerprint': entry.dataset_fingerprint,
        'target_definition': entry.target_definition,
        'aggregation_strategy': entry.aggregation_strategy,
        'training_periods': entry.training_periods,
        'validation_periods': entry.validation_periods,
        'test_periods': entry.test_periods,
        'algorithm': entry.algorithm,
        'hyperparameters': entry.hyperparameters,
        'random_seed': entry.random_seed,
        'training_timestamp': entry.training_timestamp.isoformat() if entry.training_timestamp else None,
        'validation_metrics': entry.validation_metrics,
        'artifact_identifier': entry.artifact_identifier,
        'artifact_hash': entry.artifact_hash,
        'validation_status': entry.validation_status,
        'approval_status': entry.approval_status,
        'created_by_user_id': entry.created_by_user_id,
        'created_at': entry.created_at.isoformat(),
        'notes': entry.notes,
        'deployment_status': entry.deployment_status,
        'rejected_by_user_id': entry.rejected_by_user_id,
        'rejected_at': entry.rejected_at.isoformat() if entry.rejected_at else None,
        'rejection_reason': entry.rejection_reason,
    }


@app.get(f'{settings.api_v1_prefix}/ml/phase3/candidate')
def phase3_candidate(user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    entry = db.query(ModelRegistryEntry).filter(
        ModelRegistryEntry.status == 'candidate',
        ModelRegistryEntry.artifact_identifier.is_not(None),
        ModelRegistryEntry.dataset_fingerprint.is_not(None),
    ).order_by(ModelRegistryEntry.created_at.desc()).first()
    return {'status': 'available' if entry else 'unavailable', 'candidate': candidate_registry_payload(entry) if entry else None}


@app.get(f'{settings.api_v1_prefix}/ml/phase3/evaluation')
def phase3_evaluation(user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    entry = db.query(ModelRegistryEntry).filter(
        ModelRegistryEntry.status == 'candidate',
        ModelRegistryEntry.artifact_identifier.is_not(None),
        ModelRegistryEntry.validation_metrics.is_not(None),
    ).order_by(ModelRegistryEntry.created_at.desc()).first()
    return {'status': 'available' if entry and entry.validation_metrics else 'unavailable', 'model_version': entry.model_version if entry else None, 'evaluation': entry.validation_metrics if entry else None, 'detail': None if entry else 'No validated candidate evaluation is available.'}


@app.get(f'{settings.api_v1_prefix}/ml/phase3/compare')
def phase3_compare(user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    production = production_model_registry_entry()
    entry = db.query(ModelRegistryEntry).filter(
        ModelRegistryEntry.status == 'candidate',
        ModelRegistryEntry.artifact_identifier.is_not(None),
    ).order_by(ModelRegistryEntry.created_at.desc()).first()
    production_contract = production['feature_contract']
    candidate_contract = entry.feature_schema if entry else None
    production_hash = production.get('training_dataset_hash')
    candidate_hash = entry.dataset_fingerprint if entry else None
    production_test = production.get('validation_metrics')
    candidate_test = (entry.validation_metrics or {}).get('test') if entry else None
    blockers: list[str] = []
    if entry is None:
        blockers.append('No candidate model with a registered artifact is available.')
    else:
        if candidate_contract != production_contract:
            blockers.append('Candidate and production feature contracts are not identical.')
        if not candidate_hash or not entry.dataset_id or not entry.test_periods:
            blockers.append('Candidate test evaluation is missing dataset identity, fingerprint, or temporal test-period provenance.')
        if not isinstance(candidate_test, dict) or not candidate_test.get('sample_count'):
            blockers.append('Candidate held-out test metrics are unavailable.')
        if production['training_provenance'].get('demo_data') is True:
            blockers.append('Production evaluation provenance identifies demo/synthetic training data, not the candidate test dataset.')
        if not production_hash:
            blockers.append('Production evaluation has no verifiable training dataset hash.')
        elif candidate_hash and production_hash != candidate_hash:
            blockers.append('Production and candidate dataset hashes identify different evaluation data.')
        if not isinstance(production_test, dict):
            blockers.append('Production evaluation metrics are unavailable.')
        else:
            blockers.append('Production metrics do not identify the candidate temporal test rows and cannot be treated as common-test-set metrics.')
        blockers.append('A shared test-row identity and outcome provenance cannot be verified from the production artifact metadata.')
    blockers = list(dict.fromkeys(blockers))
    feature_contract_compatible = bool(entry and candidate_contract == production_contract)
    dataset_hashes_match = bool(entry and production_hash and candidate_hash and production_hash == candidate_hash)
    return {
        'status': 'unavailable',
        'comparison': {
            'compatible': False,
            'blockers': blockers,
            'feature_contract': {
                'compatible': feature_contract_compatible,
                'production': production_contract,
                'candidate': candidate_contract,
            },
            'dataset_identity': {
                'compatible': False,
                'production_identity': production['training_provenance'].get('source'),
                'candidate_identity': entry.dataset_id if entry else None,
                'production_hash': production_hash,
                'candidate_hash': candidate_hash,
                'hashes_match': dataset_hashes_match,
                'same_temporal_test_rows_verified': False,
            },
            'common_test_set': None,
            'winner': None,
            'interpretation': 'No comparative performance claim is made unless both models are evaluated on the exact same held-out rows with compatible feature contracts and verified provenance.',
        },
        'production': {
            'model_version': production['model_version'],
            'demo_data': production['training_provenance']['demo_data'],
            'feature_contract': production_contract,
            'feature_contract_version': production['feature_contract_version'],
            'dataset_identity': production['training_provenance'].get('source'),
            'dataset_hash': production_hash,
            'training_timestamp': production.get('training_timestamp'),
            'provenance': production['training_provenance'],
            'metrics': production_test,
            'metric_context': 'Artifact-recorded production metrics only; not a comparable evaluation and not evidence validating imported academic outcomes.',
        },
        'candidate': candidate_registry_payload(entry) if entry else None,
        'candidate_test_evaluation': candidate_test,
        'candidate_test_provenance': {
            'dataset_id': entry.dataset_id,
            'dataset_version': entry.dataset_version,
            'dataset_hash': candidate_hash,
            'test_periods': entry.test_periods,
            'feature_contract': candidate_contract,
            'feature_contract_version': entry.feature_contract_version,
            'artifact_hash': entry.artifact_hash,
        } if entry else None,
    }


@app.get(f'{settings.api_v1_prefix}/ml/phase3/shap')
def phase3_candidate_shap(user: CurrentTeacher, db: Session = Depends(get_db), student_id: int | None = None) -> dict[str, Any]:
    entry = db.query(ModelRegistryEntry).filter(
        ModelRegistryEntry.status == 'candidate',
        ModelRegistryEntry.validation_status == 'passed',
    ).order_by(ModelRegistryEntry.created_at.desc()).first()
    if entry is None or not entry.artifact_identifier:
        raise HTTPException(status_code=404, detail='Candidate SHAP unavailable because no validated candidate model exists.')
    student = db.query(Student).filter(Student.id == student_id).first() if student_id is not None else None
    if student_id is not None and student is None:
        raise HTTPException(status_code=404, detail='Student not found')
    dataset = build_phase3_dataset(db, aggregation_strategy=entry.aggregation_strategy, feature_contract=entry.feature_schema)
    candidate_row = next((row for row in dataset['candidate_rows'] if row['student_identifier'] == student.student_id), None) if student else None
    if student and candidate_row is None:
        raise HTTPException(status_code=404, detail='No temporally eligible candidate dataset row exists for this student.')
    feature_values = {name: candidate_row[name] for name in entry.feature_schema} if candidate_row else {}
    try:
        artifact_path = candidate_artifact_path(entry, CANDIDATE_ARTIFACT_DIRECTORY)
    except DeploymentArtifactError as exc:
        raise HTTPException(status_code=404, detail=f'Validated candidate artifact is unavailable: {exc}') from exc
    try:
        explanation = explain_candidate(artifact_path, feature_values)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail='Candidate SHAP input does not match the validated candidate feature contract.') from exc
    return explanation


@app.post(f'{settings.api_v1_prefix}/ml/phase3/train')
def phase3_train_candidate(payload: Phase3TrainingRequest, user: CurrentTeacher, db: Session = Depends(get_db)) -> JSONResponse:
    dataset = build_phase3_dataset(
        db,
        aggregation_strategy=payload.aggregation_strategy,
        feature_contract=payload.feature_contract,
    )
    blockers = list(dataset['readiness']['blockers'])
    if not dataset['readiness']['training_ready']:
        reason = '; '.join(blockers)
        phase3_audit(
            db, user, 'phase3.training.blocked', result='blocked', reason=reason, dataset_id=dataset['dataset_id'],
            dataset_version=dataset['dataset_version'], dataset_fingerprint=dataset['dataset_fingerprint'],
        )
        return JSONResponse(status_code=409, content={'detail': {'message': 'Candidate training blocked: real-data readiness criteria are not satisfied.', 'blockers': blockers, 'dataset_id': dataset['dataset_id'], 'dataset_fingerprint': dataset['dataset_fingerprint']}})
    import pandas as pd

    candidate_frame = pd.DataFrame(dataset['candidate_rows'])
    try:
        trained = train_candidate(
            candidate_frame,
            output_directory=CANDIDATE_ARTIFACT_DIRECTORY,
            feature_contract=payload.feature_contract,
            target_column='risk_target',
            period_column='academic_period',
            identity_column='student_identifier',
            dataset_id=dataset['dataset_id'],
            dataset_version=dataset['dataset_version'],
            dataset_fingerprint=dataset['dataset_fingerprint'],
            target_definition=dataset['target_definition'],
            aggregation_strategy=payload.aggregation_strategy,
        )
    except ValueError as exc:
        reason = str(exc)
        phase3_audit(
            db, user, 'phase3.training.blocked', result='blocked', reason=reason, dataset_id=dataset['dataset_id'],
            dataset_version=dataset['dataset_version'], dataset_fingerprint=dataset['dataset_fingerprint'],
        )
        return JSONResponse(status_code=409, content={'detail': {'message': 'Candidate training blocked by temporal split or dataset validation.', 'blockers': [reason], 'dataset_id': dataset['dataset_id'], 'dataset_fingerprint': dataset['dataset_fingerprint']}})

    metadata = trained['metadata']
    entry = ModelRegistryEntry(
        model_id=metadata['model_version'],
        model_version=metadata['model_version'],
        model_type='classification',
        feature_schema=metadata['feature_contract'],
        feature_contract_version=metadata['feature_contract_version'],
        training_dataset_version=metadata['dataset_version'],
        training_dataset_hash=metadata['dataset_fingerprint'],
        training_timestamp=datetime.fromisoformat(metadata['training_timestamp']).replace(tzinfo=None),
        validation_metrics={
            'validation': metadata['validation_metrics'],
            'test': metadata['test_metrics'],
            'feature_importance': metadata['feature_importance'],
            'subgroup_evaluation': metadata['subgroup_evaluation'],
        },
        artifact_identifier=trained['artifact_path'].name,
        artifact_hash=trained['artifact_hash'],
        status='candidate',
        deployment_status='SHADOW',
        created_by_user_id=user.id,
        dataset_id=metadata['dataset_id'],
        dataset_version=metadata['dataset_version'],
        dataset_fingerprint=metadata['dataset_fingerprint'],
        target_definition=metadata['target_definition'],
        aggregation_strategy=metadata['aggregation_strategy'],
        training_periods=metadata['training_periods'],
        validation_periods=metadata['validation_periods'],
        test_periods=metadata['test_periods'],
        algorithm=metadata['algorithm'],
        hyperparameters=metadata['hyperparameters'],
        random_seed=metadata['random_seed'],
        validation_status='not_run',
        approval_status='not_approved',
        notes='Candidate artifact; production model remains unchanged pending independent governance review.',
    )
    db.add(entry)
    db.flush()
    phase3_audit(
        db, user, 'phase3.training.completed', result='candidate_created', dataset_id=dataset['dataset_id'],
        dataset_version=dataset['dataset_version'], dataset_fingerprint=dataset['dataset_fingerprint'],
        model_version=metadata['model_version'], resource_id=entry.id,
        new_state={'status': entry.status, 'validation_status': entry.validation_status, 'approval_status': entry.approval_status, 'deployment_status': entry.deployment_status},
    )
    phase3_audit(
        db, user, 'phase3.evaluation.completed', result='evaluated_on_temporal_holdouts',
        reason='validation and test metrics are recorded with split periods and sample distributions.',
        dataset_id=dataset['dataset_id'], dataset_version=dataset['dataset_version'],
        dataset_fingerprint=dataset['dataset_fingerprint'], model_version=metadata['model_version'], resource_id=entry.id,
        new_state={'status': entry.status, 'validation_status': entry.validation_status, 'approval_status': entry.approval_status, 'deployment_status': entry.deployment_status},
    )
    return JSONResponse(status_code=201, content={
        'status': 'candidate',
        'registry_entry': candidate_registry_payload(entry),
        'evaluation': {
            'validation': metadata['validation_metrics'],
            'test': metadata['test_metrics'],
            'feature_importance': metadata['feature_importance'],
            'subgroup_evaluation': metadata['subgroup_evaluation'],
        },
        'production_artifact_changed': False,
    })


def candidate_validation_blockers(entry: ModelRegistryEntry, dataset: dict[str, Any]) -> list[str]:
    blockers = list(dataset['readiness']['blockers'])
    if entry.dataset_fingerprint != dataset['dataset_fingerprint']:
        blockers.append('Candidate dataset fingerprint no longer matches the current source data.')
    required = {
        'artifact identifier': entry.artifact_identifier,
        'artifact hash': entry.artifact_hash,
        'dataset fingerprint': entry.dataset_fingerprint,
        'feature contract': entry.feature_schema,
        'target definition': entry.target_definition,
        'aggregation strategy': entry.aggregation_strategy,
        'training timestamp': entry.training_timestamp,
        'test metrics': entry.validation_metrics,
    }
    blockers.extend(f'Candidate {name} is unavailable.' for name, value in required.items() if not value)
    if entry.status != 'candidate':
        blockers.append('Only candidate registry entries may be validated.')
    try:
        candidate_artifact_path(entry, CANDIDATE_ARTIFACT_DIRECTORY)
    except DeploymentArtifactError as exc:
        blockers.append(str(exc))
    return blockers


@app.post(f'{settings.api_v1_prefix}/models/registry/{{entry_id}}/validate')
def validate_model_registry_entry(entry_id: int, user: CurrentTeacher, db: Session = Depends(get_db)) -> JSONResponse:
    entry = db.query(ModelRegistryEntry).filter(ModelRegistryEntry.id == entry_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail='Model registry entry not found.')
    try:
        dataset = build_phase3_dataset(db, aggregation_strategy=entry.aggregation_strategy, feature_contract=entry.feature_schema)
    except ValueError:
        dataset = build_phase3_dataset(db)
    blockers = candidate_validation_blockers(entry, dataset)
    previous_state = {'validation_status': entry.validation_status, 'approval_status': entry.approval_status, 'status': entry.status}
    entry.validation_status = 'blocked' if blockers else 'passed'
    phase3_audit(
        db, user, 'model.candidate.validation.blocked' if blockers else 'model.candidate.validation.passed',
        result='blocked' if blockers else 'passed', reason='; '.join(blockers) if blockers else 'Candidate validation passed.',
        dataset_id=dataset['dataset_id'], dataset_version=dataset['dataset_version'],
        dataset_fingerprint=dataset['dataset_fingerprint'], model_version=entry.model_version, resource_id=entry.id,
        previous_state=previous_state, new_state={'validation_status': entry.validation_status, 'approval_status': entry.approval_status, 'status': entry.status},
    )
    status_code = 409 if blockers else 200
    return JSONResponse(status_code=status_code, content={'detail': {'result': 'blocked' if blockers else 'passed', 'model_version': entry.model_version, 'blockers': blockers}})


class ConcurrentDeploymentError(RuntimeError):
    pass


def persisted_deployment_snapshot(db: Session) -> dict[str, Any]:
    production = production_model_registry_entry()
    state = db.query(ModelDeploymentState).filter(ModelDeploymentState.id == 1).first()
    if state is None:
        return {'model_version': production['model_version'], 'artifact_hash': production['artifact_hash'], 'deployment_status': 'PRODUCTION_FALLBACK'}
    entry = db.query(ModelRegistryEntry).filter(ModelRegistryEntry.model_version == state.active_model_version).first()
    return {
        'model_version': state.active_model_version,
        'artifact_hash': state.active_artifact_hash,
        'deployment_status': entry.deployment_status if entry else 'PRODUCTION_FALLBACK',
        'artifact_identifier': entry.artifact_identifier if entry else DEFAULT_ARTIFACT.name,
    }


def deployment_snapshot(db: Session) -> dict[str, Any]:
    production = production_model_registry_entry()
    state = db.query(ModelDeploymentState).filter(ModelDeploymentState.id == 1).first()
    if state is None:
        return {'model_version': production['model_version'], 'artifact_hash': production['artifact_hash'], 'deployment_status': 'PRODUCTION_FALLBACK'}
    path = selected_model_artifact(db)
    entry = db.query(ModelRegistryEntry).filter(ModelRegistryEntry.model_version == state.active_model_version).first()
    return {
        'model_version': state.active_model_version,
        'artifact_hash': state.active_artifact_hash,
        'deployment_status': entry.deployment_status if entry else 'PRODUCTION_FALLBACK',
        'artifact_identifier': path.name,
    }


def add_deployment_event(
    db: Session,
    user: User,
    *,
    event: str,
    previous_state: dict[str, Any],
    new_state: dict[str, Any],
    candidate: ModelRegistryEntry | None,
    reason: str,
    status: str,
    rollback_of_event_id: int | None = None,
) -> ModelDeploymentEvent:
    event_row = ModelDeploymentEvent(
        event=event,
        previous_version=previous_state.get('model_version'),
        new_version=new_state.get('model_version'),
        candidate_version=candidate.model_version if candidate else None,
        artifact_hash=candidate.artifact_hash if candidate else new_state.get('artifact_hash'),
        actor_user_id=user.id,
        actor_role=user.role.upper(),
        occurred_at=datetime.utcnow(),
        reason=reason,
        status=status,
        rollback_of_event_id=rollback_of_event_id,
        dataset_hash=candidate.dataset_fingerprint if candidate else None,
        feature_contract=candidate.feature_schema if candidate else None,
        evaluation_reference=candidate.validation_metrics if candidate else None,
        previous_state=previous_state,
        new_state=new_state,
    )
    db.add(event_row)
    if event == 'PROMOTE' and status == 'blocked':
        db.add(AuditLog(
            actor_user_id=user.id, action='model.promotion.blocked', resource_type='model_registry_entry',
            resource_id=candidate.model_version if candidate else None,
            detail={'actor_role': user.role.upper(), 'reason': reason, 'previous_state': previous_state, 'new_state': new_state},
        ))
    if event == 'ROLLBACK' and status == 'blocked':
        db.add(AuditLog(
            actor_user_id=user.id, action='model.rollback.blocked', resource_type='model_registry_entry',
            resource_id=candidate.model_version if candidate else previous_state.get('model_version'),
            detail={'actor_role': user.role.upper(), 'reason': reason, 'previous_state': previous_state, 'new_state': new_state},
        ))
    db.add(AuditLog(
        actor_user_id=user.id,
        action=f'model.deployment.{event.casefold()}.{status}',
        resource_type='model_deployment',
        resource_id=candidate.model_version if candidate else new_state.get('model_version'),
        detail={
            'event': event,
            'status': status,
            'reason': reason,
            'actor_role': user.role.upper(),
            'candidate_version': candidate.model_version if candidate else None,
            'artifact_hash': candidate.artifact_hash if candidate else new_state.get('artifact_hash'),
            'dataset_hash': candidate.dataset_fingerprint if candidate else None,
            'feature_contract': candidate.feature_schema if candidate else None,
            'evaluation_reference': candidate.validation_metrics if candidate else None,
            'rollback_of_event_id': rollback_of_event_id,
            'previous_state': previous_state,
            'new_state': new_state,
        },
    ))
    return event_row


def _apply_active_version(
    db: Session,
    *,
    previous_state: dict[str, Any],
    new_state: dict[str, Any],
) -> None:
    current = db.query(ModelDeploymentState).filter(ModelDeploymentState.id == 1).with_for_update().first()
    if current is None:
        current = ModelDeploymentState(
            id=1,
            active_model_version=previous_state['model_version'],
            active_artifact_hash=previous_state['artifact_hash'],
        )
        db.add(current)
        db.flush()
    changed = db.query(ModelDeploymentState).filter(
        ModelDeploymentState.id == 1,
        ModelDeploymentState.active_model_version == previous_state['model_version'],
        ModelDeploymentState.active_artifact_hash == previous_state['artifact_hash'],
    ).update({
        ModelDeploymentState.active_model_version: new_state['model_version'],
        ModelDeploymentState.active_artifact_hash: new_state['artifact_hash'],
        ModelDeploymentState.updated_at: datetime.utcnow(),
    }, synchronize_session=False)
    if changed != 1:
        raise ConcurrentDeploymentError('Active local model version changed during the transaction.')
    current.active_model_version = new_state['model_version']
    current.active_artifact_hash = new_state['artifact_hash']
    current.updated_at = datetime.utcnow()


@app.post(f'{settings.api_v1_prefix}/models/registry/{{entry_id}}/promote')
def promote_model_registry_entry(entry_id: int, payload: ModelPromotionRequest, user: CurrentTeacher, db: Session = Depends(get_db)) -> JSONResponse:
    entry = db.query(ModelRegistryEntry).filter(ModelRegistryEntry.id == entry_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail='Model registry entry not found.')
    try:
        dataset = build_phase3_dataset(db, aggregation_strategy=entry.aggregation_strategy, feature_contract=entry.feature_schema)
    except ValueError:
        dataset = build_phase3_dataset(db)
    try:
        previous_state = deployment_snapshot(db)
    except HTTPException as exc:
        previous_state = persisted_deployment_snapshot(db)
        active_error = str(exc.detail)
    else:
        active_error = None
    blockers = list(dataset['readiness']['blockers'])
    blockers.extend(candidate_validation_blockers(entry, dataset))
    if active_error:
        blockers.append(active_error)
    if not payload.explicit_approval:
        blockers.append('Explicit authorized deployment approval was not provided.')
    if len(payload.approval_note.strip()) < 10:
        blockers.append('A deployment reason of at least 10 characters is required.')
    if entry.status != 'candidate':
        blockers.append('Only a non-rejected candidate may be deployed.')
    if entry.validation_status != 'passed':
        blockers.append('Candidate validation has not passed.')
    if entry.approval_status != 'approved' or entry.approved_by_user_id is None or entry.approved_at is None:
        blockers.append('Candidate approval is not recorded.')
    try:
        verified_path, _ = verify_candidate_artifact(entry, CANDIDATE_ARTIFACT_DIRECTORY)
    except DeploymentArtifactError as exc:
        blockers.append(str(exc))
        verified_path = None
    if previous_state.get('model_version') == entry.model_version:
        blockers.append('This candidate is already the active local model.')
    blockers = list(dict.fromkeys(blockers))
    if blockers:
        reason = '; '.join(blockers)
        unchanged_state = dict(previous_state)
        add_deployment_event(
            db, user, event='PROMOTE', previous_state=previous_state, new_state=unchanged_state,
            candidate=entry, reason=reason, status='blocked',
        )
        db.commit()
        return JSONResponse(status_code=409, content={'detail': {'result': 'blocked', 'message': 'Local model deployment blocked by readiness, governance, or artifact compatibility checks.', 'blockers': blockers}})

    if verified_path is None:
        raise HTTPException(status_code=500, detail='Candidate passed deployment checks without a verified artifact path.')
    new_state = {
        'model_version': entry.model_version,
        'artifact_hash': entry.artifact_hash,
        'deployment_status': 'LOCAL_ACTIVE',
        'artifact_identifier': verified_path.name,
    }
    try:
        _apply_active_version(db, previous_state=previous_state, new_state=new_state)
        old_entry = db.query(ModelRegistryEntry).filter(ModelRegistryEntry.model_version == previous_state['model_version']).first()
        if old_entry is not None:
            old_entry.deployment_status = 'SHADOW'
        entry.deployment_status = 'LOCAL_ACTIVE'
        entry.previous_production_model_version = previous_state['model_version']
        entry.promoted_at = datetime.utcnow()
        entry.retired_at = None
        add_deployment_event(
            db, user, event='PROMOTE', previous_state=previous_state, new_state=new_state,
            candidate=entry, reason=payload.approval_note, status='succeeded',
        )
        db.commit()
    except (IntegrityError, ConcurrentDeploymentError):
        db.rollback()
        return JSONResponse(status_code=409, content={'detail': {'result': 'blocked', 'message': 'Concurrent local deployment state change; no deployment was applied.', 'blockers': ['Active version changed during deployment.']}})
    return JSONResponse(status_code=200, content={
        'result': 'deployed', 'deployment_target': 'LOCAL', 'active_model_version': entry.model_version,
        'artifact_hash': entry.artifact_hash, 'production_artifact_changed': False,
    })


@app.post(f'{settings.api_v1_prefix}/models/registry/{{entry_id}}/approve')
def approve_model_registry_entry(entry_id: int, payload: ModelApprovalRequest, user: CurrentTeacher, db: Session = Depends(get_db)) -> JSONResponse:
    entry = db.query(ModelRegistryEntry).filter(ModelRegistryEntry.id == entry_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail='Model registry entry not found.')
    try:
        dataset = build_phase3_dataset(db, aggregation_strategy=entry.aggregation_strategy, feature_contract=entry.feature_schema)
    except ValueError:
        dataset = build_phase3_dataset(db)
    previous_state = {'validation_status': entry.validation_status, 'approval_status': entry.approval_status, 'status': entry.status}
    blockers = candidate_validation_blockers(entry, dataset)
    if entry.validation_status != 'passed':
        blockers.append('Candidate validation has not passed.')
    if not payload.explicit_approval:
        blockers.append('Explicit candidate approval was not provided.')
    if blockers:
        reason = '; '.join(blockers)
        phase3_audit(
            db, user, 'model.candidate.approval.blocked', result='blocked', reason=reason,
            dataset_id=dataset['dataset_id'], dataset_version=dataset['dataset_version'],
            dataset_fingerprint=dataset['dataset_fingerprint'], model_version=entry.model_version,
            resource_id=entry.id, previous_state=previous_state, new_state=previous_state,
        )
        return JSONResponse(status_code=409, content={'detail': {'result': 'blocked', 'message': 'Candidate approval blocked by readiness or validation gates.', 'blockers': blockers}})
    entry.approval_status = 'approved'
    entry.approved_by_user_id = user.id
    entry.approved_at = datetime.utcnow()
    entry.notes = f'{entry.notes or ""}\nApproval note: {payload.approval_note}'.strip()
    phase3_audit(
        db, user, 'model.candidate.approval.granted', result='approved_for_review', reason=payload.approval_note,
        dataset_id=dataset['dataset_id'], dataset_version=dataset['dataset_version'],
        dataset_fingerprint=dataset['dataset_fingerprint'], model_version=entry.model_version,
        resource_id=entry.id, previous_state=previous_state,
        new_state={'validation_status': entry.validation_status, 'approval_status': entry.approval_status, 'status': entry.status},
    )
    return JSONResponse(status_code=200, content={'result': 'approved', 'model_version': entry.model_version, 'approval_status': entry.approval_status, 'approved_by_user_id': entry.approved_by_user_id, 'approved_at': entry.approved_at.isoformat(), 'production_changed': False})


@app.post(f'{settings.api_v1_prefix}/models/registry/{{entry_id}}/reject')
def reject_model_registry_entry(entry_id: int, payload: ModelRejectionRequest, user: CurrentTeacher, db: Session = Depends(get_db)) -> JSONResponse:
    entry = db.query(ModelRegistryEntry).filter(ModelRegistryEntry.id == entry_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail='Model registry entry not found.')
    previous_state = {'status': entry.status, 'deployment_status': entry.deployment_status, 'approval_status': entry.approval_status}
    active = persisted_deployment_snapshot(db)
    rejection_blockers = []
    if entry.status != 'candidate':
        rejection_blockers.append('Only a candidate registry entry can be rejected.')
    if active['model_version'] == entry.model_version:
        rejection_blockers.append('The active local model cannot be rejected; roll it back first.')
    if rejection_blockers:
        reason = '; '.join(rejection_blockers)
        add_deployment_event(
            db, user, event='REJECT', previous_state=active, new_state=active, candidate=entry,
            reason=reason, status='blocked',
        )
        db.commit()
        return JSONResponse(status_code=409, content={'detail': {'result': 'blocked', 'message': 'Candidate rejection was blocked.', 'blockers': rejection_blockers}})
    entry.status = 'rejected'
    entry.deployment_status = 'REJECTED'
    entry.rejected_by_user_id = user.id
    entry.rejected_at = datetime.utcnow()
    entry.rejection_reason = payload.rejection_reason
    new_state = {'status': entry.status, 'deployment_status': entry.deployment_status, 'approval_status': entry.approval_status}
    add_deployment_event(
        db, user, event='REJECT', previous_state=active, new_state=active, candidate=entry,
        reason=payload.rejection_reason, status='rejected',
    )
    db.add(AuditLog(
        actor_user_id=user.id, action='model.candidate.rejected', resource_type='model_registry_entry',
        resource_id=str(entry.id), detail={
            'actor_role': user.role.upper(), 'reason': payload.rejection_reason,
            'previous_state': previous_state, 'new_state': new_state,
            'active_model_version': active['model_version'], 'dataset_hash': entry.dataset_fingerprint,
            'feature_contract': entry.feature_schema, 'evaluation_reference': entry.validation_metrics,
        },
    ))
    db.commit()
    return JSONResponse(status_code=200, content={'result': 'rejected', 'model_version': entry.model_version, 'status': entry.status, 'production_changed': False})


@app.post(f'{settings.api_v1_prefix}/models/registry/{{entry_id}}/rollback')
def rollback_model_registry_entry(entry_id: int, payload: ModelRollbackRequest, user: CurrentTeacher, db: Session = Depends(get_db)) -> JSONResponse:
    entry = db.query(ModelRegistryEntry).filter(ModelRegistryEntry.id == entry_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail='Model registry entry not found.')
    previous_state = persisted_deployment_snapshot(db)
    if not payload.explicit_approval:
        reason = 'Explicit faculty approval is required for local rollback.'
        add_deployment_event(
            db, user, event='ROLLBACK', previous_state=previous_state, new_state=previous_state,
            candidate=entry, reason=reason, status='blocked',
        )
        db.commit()
        return JSONResponse(status_code=409, content={'detail': {'result': 'blocked', 'message': reason, 'blockers': [reason]}})
    blockers: list[str] = []
    production = production_model_registry_entry()
    if entry.model_version != previous_state['model_version'] or entry.deployment_status != 'LOCAL_ACTIVE':
        blockers.append('The requested registry entry is not the active local deployment.')
    if previous_state['model_version'] == production['model_version']:
        blockers.append('Rollback unavailable: no verified prior local deployment exists.')
    deployed_event = None
    if not blockers:
        deployed_event = db.query(ModelDeploymentEvent).filter(
            ModelDeploymentEvent.event == 'PROMOTE',
            ModelDeploymentEvent.status == 'succeeded',
            ModelDeploymentEvent.new_version == previous_state['model_version'],
        ).order_by(ModelDeploymentEvent.id.desc()).first()
        if deployed_event is None or not deployed_event.previous_version:
            blockers.append('Rollback unavailable: no verified prior deployment is recorded.')
    target_version = deployed_event.previous_version if deployed_event else previous_state['model_version']
    target_entry = db.query(ModelRegistryEntry).filter(ModelRegistryEntry.model_version == target_version).first() if target_version else None
    if not blockers and target_version == production['model_version']:
        previous_hash = (deployed_event.previous_state or {}).get('artifact_hash')
        try:
            production_hash_matches = sha256_file(DEFAULT_ARTIFACT).casefold() == str(production['artifact_hash']).casefold()
        except OSError:
            production_hash_matches = False
        if previous_hash != production['artifact_hash'] or not production_hash_matches:
            blockers.append('Rollback target production artifact hash is unavailable or changed.')
        new_state = {'model_version': target_version, 'artifact_hash': production['artifact_hash'], 'deployment_status': 'PRODUCTION_FALLBACK', 'artifact_identifier': DEFAULT_ARTIFACT.name}
    elif not blockers:
        if target_entry is None or target_entry.status != 'candidate' or target_entry.deployment_status == 'REJECTED':
            blockers.append('Rollback target registry candidate is unavailable or rejected.')
        elif target_entry.validation_status != 'passed' or target_entry.approval_status != 'approved':
            blockers.append('Rollback target no longer has passed validation and recorded approval.')
        target_hash = (deployed_event.previous_state or {}).get('artifact_hash') if deployed_event else None
        if not blockers and (not target_hash or target_entry is None or target_entry.artifact_hash != target_hash):
            blockers.append('Rollback target artifact hash does not match its prior deployment record.')
        target_path = None
        if not blockers and target_entry is not None:
            try:
                target_path, _ = verify_candidate_artifact(target_entry, CANDIDATE_ARTIFACT_DIRECTORY)
            except DeploymentArtifactError as exc:
                blockers.append(f'Rollback target verification failed: {exc}')
        new_state = {
            'model_version': target_version,
            'artifact_hash': target_hash,
            'deployment_status': 'LOCAL_ACTIVE',
            'artifact_identifier': target_path.name if target_path else None,
        }
    else:
        new_state = dict(previous_state)
    if blockers:
        reason = '; '.join(blockers)
        add_deployment_event(
            db, user, event='ROLLBACK', previous_state=previous_state, new_state=previous_state,
            candidate=entry, reason=reason, status='blocked',
            rollback_of_event_id=deployed_event.id if deployed_event else None,
        )
        db.commit()
        return JSONResponse(status_code=409, content={'detail': {'result': 'blocked', 'message': 'Rollback is unavailable because no verified prior deployment can be restored.', 'blockers': blockers}})
    try:
        _apply_active_version(db, previous_state=previous_state, new_state=new_state)
        entry.deployment_status = 'SHADOW'
        entry.retired_at = datetime.utcnow()
        if target_entry is not None:
            target_entry.deployment_status = 'LOCAL_ACTIVE'
            target_entry.retired_at = None
        add_deployment_event(
            db, user, event='ROLLBACK', previous_state=previous_state, new_state=new_state,
            candidate=target_entry, reason=payload.rollback_note, status='succeeded',
            rollback_of_event_id=deployed_event.id if deployed_event else None,
        )
        db.commit()
    except (IntegrityError, ConcurrentDeploymentError):
        db.rollback()
        return JSONResponse(status_code=409, content={'detail': {'result': 'blocked', 'message': 'Concurrent local deployment state change; rollback was not applied.'}})
    return JSONResponse(status_code=200, content={'result': 'rolled_back', 'deployment_target': 'LOCAL', 'active_model_version': target_version, 'rollback_of_event_id': deployed_event.id if deployed_event else None})


@app.get(f'{settings.api_v1_prefix}/models/deployments')
def model_deployment_history(user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        active = deployment_snapshot(db)
    except HTTPException as exc:
        raise HTTPException(status_code=503, detail=f'Active deployment is unsafe or unavailable: {exc.detail}') from exc
    events = db.query(ModelDeploymentEvent).order_by(ModelDeploymentEvent.id.desc()).all()
    return {
        'deployment_target': 'LOCAL',
        'active': active,
        'history': [{
            'id': item.id, 'event': item.event, 'previous_version': item.previous_version,
            'new_version': item.new_version, 'candidate_version': item.candidate_version,
            'artifact_hash': item.artifact_hash, 'actor_user_id': item.actor_user_id,
            'actor_role': item.actor_role, 'occurred_at': item.occurred_at.isoformat(),
            'reason': item.reason, 'status': item.status,
            'rollback_of_event_id': item.rollback_of_event_id, 'dataset_hash': item.dataset_hash,
            'feature_contract': item.feature_contract, 'evaluation_reference': item.evaluation_reference,
            'previous_state': item.previous_state, 'new_state': item.new_state,
        } for item in events],
    }


@app.get(f'{settings.api_v1_prefix}/ml/phase3/audit')
def phase3_governance_audit(
    user: CurrentTeacher,
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    entries = db.query(AuditLog).filter(
        AuditLog.resource_type.in_(['phase3_model_governance', 'model_deployment', 'model_registry_entry']),
    ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).all()
    return {
        'items': [{
            'id': item.id,
            'actor_user_id': item.actor_user_id,
            'action': item.action,
            'resource_type': item.resource_type,
            'resource_id': item.resource_id,
            'occurred_at': item.created_at.isoformat(),
            'detail': item.detail,
        } for item in entries],
    }


@app.get(f'{settings.api_v1_prefix}/risk/monitoring')
def risk_monitoring(user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    students = db.query(Student).all()
    current_predictions = [student_risk_view(student, db)[1] for student in students]
    counts = {level: sum(prediction['risk_level'] == level for prediction in current_predictions) for level in ('HIGH', 'MEDIUM', 'LOW')}
    history = db.query(RiskSnapshot).order_by(RiskSnapshot.recorded_at).all()
    transition_report = risk_transition_report(db)
    transitions = [{
        **item,
        'name': item['student_name'],
        'from': item['previous_risk'],
        'to': item['new_risk'],
    } for item in transition_report['transitions']]
    momentum = {level: 0 for level in ('IMPROVING', 'STABLE', 'DECLINING', 'VOLATILE', 'INSUFFICIENT_DATA')}
    for student in students:
        observations = db.query(AcademicMomentum.value).filter(AcademicMomentum.student_id == student.id, AcademicMomentum.metric == 'assessment').order_by(AcademicMomentum.observed_at).all()
        level = calculate_momentum([row[0] for row in observations])['classification']
        momentum[level] = momentum.get(level, 0) + 1
    return {'distribution': counts, 'momentum': momentum, 'transitions': transitions, 'transition_history_status': transition_report['history_status'], 'students_with_insufficient_transition_history': transition_report['students_with_insufficient_history'], 'history_note': 'Historical saved class labels; they may predate the current argmax policy. Current distribution is calculated from the current model.', 'history': [{'student_id': item.student_id, 'risk_level': item.risk_level, 'recorded_at': item.recorded_at.isoformat()} for item in history]}


@app.get(f'{settings.api_v1_prefix}/risk/high-risk-demo')
def high_risk_demo(user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    candidates = []
    try:
        for student in db.query(Student).order_by(Student.student_id).all():
            features = student_features(student, db)
            prediction = predict_with_active_model(features, db)
            candidates.append((student, features, prediction))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail='Risk model is not trained. Run the documented training command first.') from exc
    if not candidates:
        raise HTTPException(status_code=404, detail='No existing student records are available for the demonstration.')
    predicted_high = [item for item in candidates if item[2]['risk_level'] == 'HIGH']
    selection_pool = predicted_high or candidates
    student, features, prediction = min(
        selection_pool,
        key=lambda item: (-item[2]['class_probabilities'].get('HIGH', 0.0), item[0].student_id.casefold()),
    )
    try:
        explanation = explain_with_active_model(features, db, target_class=prediction['risk_level'])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail='SHAP model background is unavailable.') from exc
    return {
        'student': {'id': student.id, 'student_id': student.student_id, 'full_name': student.full_name},
        'prediction': prediction,
        'features': features,
        'explanation': explanation,
        'high_risk_available': bool(predicted_high),
        'selection_note': 'Highest current P(HIGH) among existing model-predicted HIGH students.' if predicted_high else 'No current prediction is HIGH; showing the existing student with the highest P(HIGH) without changing the canonical prediction.',
    }


@app.get(f'{settings.api_v1_prefix}/early-warnings')
def early_warnings(user: CurrentTeacher, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    warnings = []
    for student in db.query(Student).all():
        features = student_features(student, db)
        prediction = predict_with_active_model(features, db)
        context = {'student_id': student.id, 'name': student.full_name, 'department': student.department, 'course': student.course.code if student.course else None, 'detected_at': datetime.utcnow().isoformat(), 'risk_level': prediction['risk_level'], 'risk_probability': prediction['risk_probability']}
        snapshots = db.query(RiskSnapshot).filter(RiskSnapshot.student_id == student.id).order_by(RiskSnapshot.recorded_at).all()
        if prediction['risk_level'] == 'HIGH':
            warnings.append({**context, 'severity': 'HIGH', 'signal': 'High risk', 'change': f'{prediction["risk_probability"]:.0%} probability of HIGH', 'reason': 'Current academic risk rating requires a faculty check-in.'})
        if len(snapshots) > 1:
            previous, current = snapshots[-2], snapshots[-1]
            order = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}
            if order.get(current.risk_level, 0) > order.get(previous.risk_level, 0):
                warnings.append({**context, 'severity': current.risk_level, 'signal': 'Risk increase', 'change': f'{previous.risk_level} to {current.risk_level}', 'reason': 'Consecutive saved risk snapshots show an increased level.'})
            if previous.risk_level != 'HIGH' and current.risk_level == 'HIGH':
                warnings.append({**context, 'severity': 'HIGH', 'signal': 'New high risk', 'change': f'{previous.risk_level} to HIGH', 'reason': 'A new saved snapshot entered the high-risk category.'})
        if features['attendance_change'] < -10:
            warnings.append({**context, 'severity': 'HIGH' if features['attendance_change'] < -20 else 'MEDIUM', 'signal': 'Attendance decline', 'change': f'{features["attendance_change"]:.1f}% recent change', 'reason': 'Dated attendance observations are declining.'})
        if features['assessment_change'] < -10:
            warnings.append({**context, 'severity': 'HIGH' if features['assessment_change'] < -20 else 'MEDIUM', 'signal': 'Assessment decline', 'change': f'{features["assessment_change"]:.1f}% recent change', 'reason': 'Dated assessment observations are declining.'})
        for metric, signal_name in (('activity', 'Activity decline'), ('assignment_submission', 'Assignment decline')):
            history = db.query(AcademicMomentum.value).filter(AcademicMomentum.student_id == student.id, AcademicMomentum.metric == metric).order_by(AcademicMomentum.observed_at).all()
            trend = calculate_momentum([item[0] for item in history])
            if trend['classification'] == 'DECLINING':
                warnings.append({**context, 'severity': 'MEDIUM', 'signal': signal_name, 'change': f'{trend["percent_change"]:.1f}% recent change' if trend['percent_change'] is not None else 'Declining trend', 'reason': f'Dated {metric.replace("_", " ")} observations are declining.'})
        if features['missing_submissions'] > 0:
            warnings.append({**context, 'severity': 'MEDIUM', 'signal': 'Missing submissions', 'change': f'{int(features["missing_submissions"])} missing', 'reason': 'Assigned work has no recorded submission.'})
    return warnings


@app.get(f'{settings.api_v1_prefix}/risk/feature-importance')
def risk_feature_importance(user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = [student_features(student, db) for student in db.query(Student).limit(100).all()]
    try:
        return global_importance(rows)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail='Risk model is not trained. Run the documented training command first.') from exc


@app.get(f'{settings.api_v1_prefix}/assignments', response_model=list[AssignmentOut])
def list_assignments(user: CurrentUser, db: Session = Depends(get_db), subject_code: str | None = None) -> list[Assignment]:
    query = db.query(Assignment)
    if subject_code:
        subject = db.query(Subject).filter(Subject.code == subject_code.upper()).first()
        if subject is None:
            raise HTTPException(status_code=404, detail='Subject not found')
        query = query.filter(Assignment.subject_id == subject.id)
    if user.role.upper() == 'STUDENT':
        student = db.query(Student).filter(Student.user_id == user.id).first()
        if student is None:
            raise HTTPException(status_code=403, detail='Student profile is not linked')
        assigned_ids = select(AssignmentStudent.assignment_id).where(AssignmentStudent.student_id == student.id)
        query = query.filter((Assignment.status == 'active') & ((Assignment.id.in_(assigned_ids)) | (Assignment.section == student.section)))
    return query.order_by(Assignment.due_date).all()


def resolve_assignment_subject(db: Session, subject_name: str) -> tuple[int | None, str]:
    subject = db.query(Subject).filter((Subject.code.ilike(subject_name)) | (Subject.name.ilike(subject_name))).first()
    if subject:
        return subject.id, subject.name
    if db.query(Subject.id).first():
        raise HTTPException(status_code=422, detail='Choose a subject from the institutional subject list.')
    return None, subject_name


@app.post(f'{settings.api_v1_prefix}/assignments', response_model=AssignmentOut, status_code=201)
def create_assignment(payload: AssignmentCreate, user: CurrentTeacher, db: Session = Depends(get_db)) -> Assignment:
    values = payload.model_dump()
    if values['max_marks'] > 25:
        raise HTTPException(status_code=422, detail='New assignments cannot exceed 25 marks.')
    subject_id, subject_name = resolve_assignment_subject(db, values['subject'])
    values.update(subject=subject_name, subject_id=subject_id)
    assignment = Assignment(**values)
    db.add(assignment)
    db.flush()
    audit(db, user, 'assignment.created', 'assignment', assignment.id)
    eligible_students = db.query(Student).filter(Student.section == assignment.section).all() if assignment.section else db.query(Student).all()
    for student in eligible_students:
        db.add(AssignmentStudent(assignment_id=assignment.id, student_id=student.id))
        if student.user_id:
            db.add(Notification(user_id=student.user_id, kind='assignment', title='New assignment', body=assignment.title, metadata_json={'assignment_id': assignment.id}))
    db.commit()
    db.refresh(assignment)
    return assignment


@app.post(f'{settings.api_v1_prefix}/assignments/{{assignment_id}}/duplicate', response_model=AssignmentOut, status_code=201)
def duplicate_assignment(assignment_id: int, user: CurrentTeacher, db: Session = Depends(get_db)) -> Assignment:
    original = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if original is None:
        raise HTTPException(status_code=404, detail='Assignment not found')
    duplicate = Assignment(
        title=f'{original.title} (copy)', subject=original.subject, course=original.course, section=original.section,
        subject_id=original.subject_id,
        description=original.description, instructions=original.instructions, start_date=original.start_date,
        due_date=original.due_date, max_marks=original.max_marks, status='draft',
        allowed_file_types=original.allowed_file_types, max_file_size=original.max_file_size, rubric_id=original.rubric_id,
    )
    db.add(duplicate)
    audit(db, user, 'assignment.duplicated', 'assignment', original.id)
    db.commit()
    db.refresh(duplicate)
    return duplicate


@app.patch(f'{settings.api_v1_prefix}/assignments/{{assignment_id}}/status', response_model=AssignmentOut)
def change_assignment_status(assignment_id: int, payload: AssignmentStatusUpdate, user: CurrentTeacher, db: Session = Depends(get_db)) -> Assignment:
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail='Assignment not found')
    assignment.status = payload.status
    audit(db, user, f'assignment.{payload.status}', 'assignment', assignment.id)
    db.commit()
    db.refresh(assignment)
    return assignment


@app.patch(f'{settings.api_v1_prefix}/assignments/{{assignment_id}}', response_model=AssignmentOut)
def update_assignment(assignment_id: int, payload: AssignmentCreate, user: CurrentTeacher, db: Session = Depends(get_db)) -> Assignment:
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail='Assignment not found')
    values = payload.model_dump()
    if values['max_marks'] > max(25, assignment.max_marks):
        raise HTTPException(status_code=422, detail='Assignment maximum cannot be increased above 25 marks.')
    subject_id, subject_name = resolve_assignment_subject(db, values['subject'])
    values.update(subject=subject_name, subject_id=subject_id)
    for key, value in values.items():
        setattr(assignment, key, value)
    audit(db, user, 'assignment.updated', 'assignment', assignment.id)
    db.commit()
    db.refresh(assignment)
    return assignment


@app.get(f'{settings.api_v1_prefix}/submissions', response_model=list[SubmissionOut])
def list_submissions(user: CurrentUser, db: Session = Depends(get_db)) -> list[Submission]:
    query = db.query(Submission)
    if user.role.upper() == 'STUDENT':
        student = db.query(Student).filter(Student.user_id == user.id).first()
        query = query.filter(Submission.student_id == student.id if student else -1)
    return query.order_by(Submission.submitted_at.desc()).all()


@app.post(f'{settings.api_v1_prefix}/submissions', response_model=SubmissionOut, status_code=201)
async def submit_assignment(
    student: CurrentStudent,
    db: Session = Depends(get_db),
    assignment_id: int = Form(...),
    file: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
) -> Submission:
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id, Assignment.status == 'active').first()
    if assignment is None:
        raise HTTPException(status_code=404, detail='Active assignment not found')
    assigned = db.query(AssignmentStudent.id).filter(AssignmentStudent.assignment_id == assignment.id, AssignmentStudent.student_id == student.id).first()
    if assigned is None and assignment.section != student.section:
        raise HTTPException(status_code=403, detail='Assignment is not assigned to this student')
    late = bool(assignment.due_date and datetime.utcnow() > assignment.due_date)
    existing = db.query(Submission).filter(Submission.assignment_id == assignment.id, Submission.student_id == student.id).first()
    if existing is not None and existing.status == 'graded':
        raise HTTPException(status_code=409, detail='Graded submissions cannot be replaced')
    page_files = files or ([file] if file else [])
    if not page_files:
        raise HTTPException(status_code=400, detail='Upload at least one assignment file.')
    saved_pages = []
    try:
        for page_file in page_files:
            saved_pages.append(await store_submission(page_file, student.id, assignment, settings))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if existing is None:
        existing = Submission(student_id=student.id, assignment_id=assignment.id)
        db.add(existing)
        db.flush()
    version = db.query(SubmissionVersion).filter(SubmissionVersion.submission_id == existing.id).count()
    for page_number, (saved_path, original_name) in enumerate(saved_pages, start=1):
        db.add(SubmissionVersion(
            submission_id=existing.id,
            version_number=version + page_number,
            page_number=page_number,
            page_count=len(saved_pages),
            file_name=original_name,
            stored_path=str(saved_path),
        ))
    existing.file_name = ', '.join(original_name for _, original_name in saved_pages)[:255]
    existing.stored_path = str(saved_pages[-1][0])
    existing.page_count = len(saved_pages)
    existing.submitted_at = datetime.utcnow()
    existing.status = 'late' if late else 'submitted'
    actor = db.query(User).filter(User.id == student.user_id).first()
    if actor:
        audit(db, actor, 'submission.created', 'submission', existing.id)
    db.commit()
    db.refresh(existing)
    return existing


@app.get(f'{settings.api_v1_prefix}/assignments/{{assignment_id}}/submissions', response_model=list[SubmissionOut])
def assignment_submissions(assignment_id: int, user: CurrentTeacher, db: Session = Depends(get_db)) -> list[Submission]:
    if db.query(Assignment.id).filter(Assignment.id == assignment_id).first() is None:
        raise HTTPException(status_code=404, detail='Assignment not found')
    return db.query(Submission).filter(Submission.assignment_id == assignment_id).all()


@app.get(f'{settings.api_v1_prefix}/assignments/{{assignment_id}}/summary')
def assignment_summary(assignment_id: int, user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail='Assignment not found')
    students = db.query(Student).join(AssignmentStudent).filter(AssignmentStudent.assignment_id == assignment.id).all()
    submissions = db.query(Submission).filter(Submission.assignment_id == assignment.id).all()
    counts = {name: 0 for name in ('assigned', 'submitted', 'pending', 'not_submitted', 'late', 'graded')}
    counts['assigned'] = len(students)
    counts['submitted'] = sum(bool(item.stored_path) and item.status in {'submitted', 'late', 'graded'} for item in submissions)
    counts['late'] = sum(bool(item.stored_path) and item.status == 'late' for item in submissions)
    counts['graded'] = sum(bool(item.stored_path) and item.status == 'graded' for item in submissions)
    submissions_by_student = {item.student_id: item for item in submissions}
    tracking = []
    for item in students:
        submission = submissions_by_student.get(item.id)
        uploaded = bool(submission and submission.stored_path)
        status = submission.status if uploaded and submission else 'not_submitted'
        if not uploaded:
            counts['not_submitted'] += 1
        tracking.append({
            'id': item.id,
            'student_id': item.student_id,
            'name': item.full_name,
            'department': item.department,
            'section': item.section,
            'uploaded': uploaded,
            'status': status,
            'pages': submission.page_count if uploaded and submission else 0,
            'submitted_at': submission.submitted_at.isoformat() if uploaded and submission and submission.submitted_at else None,
            'deadline': assignment.due_date.isoformat() if assignment.due_date else None,
            'grade': submission.grade if submission else None,
            'feedback': submission.feedback if submission else None,
            'submission_id': submission.id if submission else None,
        })
    counts['pending'] = counts['not_submitted']
    return {'assignment': AssignmentOut.model_validate(assignment).model_dump(), 'counts': counts, 'students': tracking}


@app.post(f'{settings.api_v1_prefix}/assignments/{{assignment_id}}/rubric', status_code=201)
def create_rubric(assignment_id: int, payload: RubricCreate, user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail='Assignment not found')
    if sum(item.maximum_score for item in payload.criteria) > assignment.max_marks:
        raise HTTPException(status_code=422, detail='Rubric total exceeds the assignment maximum')
    rubric = db.query(Rubric).filter(Rubric.id == assignment.rubric_id).first() if assignment.rubric_id else None
    if rubric is None:
        rubric = Rubric(title=payload.title)
        db.add(rubric)
    else:
        rubric.criteria.clear()
        rubric.title = payload.title
    rubric.criteria = [RubricCriterion(name=item.name, maximum_score=item.maximum_score) for item in payload.criteria]
    db.flush()
    assignment.rubric_id = rubric.id
    audit(db, user, 'rubric.created', 'assignment', assignment.id)
    db.commit()
    return {'id': rubric.id, 'title': rubric.title, 'criteria': [{'id': item.id, 'name': item.name, 'maximum_score': item.maximum_score} for item in rubric.criteria]}


@app.get(f'{settings.api_v1_prefix}/assignments/{{assignment_id}}/rubric')
def get_rubric(assignment_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> dict[str, Any]:
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if assignment is None or assignment.rubric_id is None:
        raise HTTPException(status_code=404, detail='Rubric not found')
    rubric = db.query(Rubric).filter(Rubric.id == assignment.rubric_id).first()
    return {'id': rubric.id, 'title': rubric.title, 'criteria': [{'id': item.id, 'name': item.name, 'maximum_score': item.maximum_score} for item in rubric.criteria]}


@app.post(f'{settings.api_v1_prefix}/assignments/{{assignment_id}}/reminders')
def send_assignment_reminders(assignment_id: int, student_ids: list[int], user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, int]:
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail='Assignment not found')
    pending = db.query(Student).join(AssignmentStudent).filter(AssignmentStudent.assignment_id == assignment_id, Student.id.in_(student_ids)).all()
    created = 0
    for student in pending:
        has_submission = db.query(Submission.id).filter(Submission.assignment_id == assignment_id, Submission.student_id == student.id).first()
        if not has_submission and student.user_id:
            db.add(Notification(user_id=student.user_id, kind='deadline', title='Assignment reminder', body=f'Reminder: {assignment.title} is awaiting your submission.', metadata_json={'assignment_id': assignment.id}))
            created += 1
    audit(db, user, 'assignment.reminders_sent', 'assignment', assignment_id)
    db.commit()
    return {'reminders_created': created}


@app.get(f'{settings.api_v1_prefix}/submissions/{{submission_id}}/versions')
def submission_versions(submission_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    owner_id = db.query(Student.user_id).filter(Student.id == submission.student_id).scalar() if submission else None
    if submission is None or (user.role.upper() == 'STUDENT' and owner_id != user.id):
        raise HTTPException(status_code=404, detail='Submission not found')
    versions = db.query(SubmissionVersion).filter(SubmissionVersion.submission_id == submission.id).order_by(SubmissionVersion.version_number.desc()).all()
    return [{'id': item.id, 'version_number': item.version_number, 'page_number': item.page_number, 'page_count': item.page_count, 'file_name': item.file_name, 'submitted_at': item.submitted_at.isoformat()} for item in versions]


@app.get(f'{settings.api_v1_prefix}/submissions/{{submission_id}}/versions/{{version_id}}/file')
def download_submission_version(submission_id: int, version_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> FileResponse:
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    owner_id = db.query(Student.user_id).filter(Student.id == submission.student_id).scalar() if submission else None
    if submission is None or (user.role.upper() == 'STUDENT' and owner_id != user.id):
        raise HTTPException(status_code=404, detail='Submission not found')
    version = db.query(SubmissionVersion).filter_by(id=version_id, submission_id=submission.id).first()
    if version is None:
        raise HTTPException(status_code=404, detail='Submission page not found')
    file_path = Path(version.stored_path).resolve()
    root = settings.upload_directory.resolve()
    if root not in file_path.parents or not file_path.is_file():
        raise HTTPException(status_code=404, detail='Submission file not found')
    media_type = mimetypes.guess_type(version.file_name)[0] or 'application/octet-stream'
    safe_inline = media_type in {'application/pdf', 'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'text/plain'}
    return FileResponse(file_path, filename=version.file_name, media_type=media_type, content_disposition_type='inline' if safe_inline else 'attachment')


@app.get(f'{settings.api_v1_prefix}/submissions/{{submission_id}}/file')
def download_submission(submission_id: int, user: CurrentUser, db: Session = Depends(get_db), inline: bool = False) -> FileResponse:
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    student_owner = db.query(Student.user_id).filter(Student.id == submission.student_id).scalar() if submission else None
    if submission is None or (user.role.upper() == 'STUDENT' and student_owner != user.id):
        raise HTTPException(status_code=404, detail='Submission not found')
    file_path = Path(submission.stored_path or '').resolve()
    root = settings.upload_directory.resolve()
    if root not in file_path.parents or not file_path.is_file():
        raise HTTPException(status_code=404, detail='Submission file not found')
    media_type = mimetypes.guess_type(submission.file_name or file_path.name)[0] or 'application/octet-stream'
    safe_inline = inline and media_type in {'application/pdf', 'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'text/plain'}
    return FileResponse(file_path, filename=submission.file_name or file_path.name, media_type=media_type, content_disposition_type='inline' if safe_inline else 'attachment')


@app.patch(f'{settings.api_v1_prefix}/submissions/{{submission_id}}/grade', response_model=SubmissionOut)
def grade_submission(submission_id: int, payload: GradeRequest, user: CurrentTeacher, db: Session = Depends(get_db)) -> Submission:
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if submission is None:
        raise HTTPException(status_code=404, detail='Submission not found')
    assignment = db.query(Assignment).filter(Assignment.id == submission.assignment_id).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail='Assignment not found')
    rubric_total = 0.0
    if payload.rubric_scores:
        if assignment.rubric_id is None:
            raise HTTPException(status_code=422, detail='This assignment has no rubric')
        criteria = {item.id: item for item in db.query(RubricCriterion).filter(RubricCriterion.rubric_id == assignment.rubric_id).all()}
        if set(payload.rubric_scores) - set(criteria):
            raise HTTPException(status_code=422, detail='A rubric criterion does not belong to this assignment')
        for criterion_id, score in payload.rubric_scores.items():
            criterion = criteria[criterion_id]
            if score < 0 or score > criterion.maximum_score:
                raise HTTPException(status_code=422, detail=f'Score exceeds the maximum for {criterion.name}')
            rubric_total += score
            existing_score = db.query(RubricScore).filter(RubricScore.submission_id == submission.id, RubricScore.criterion_id == criterion_id).first()
            if existing_score:
                existing_score.score = score
            else:
                db.add(RubricScore(submission_id=submission.id, criterion_id=criterion_id, score=score))
    final_grade = rubric_total if payload.rubric_scores else payload.grade
    if final_grade > assignment.max_marks:
        raise HTTPException(status_code=422, detail='Grade exceeds assignment maximum')
    submission.grade = final_grade
    submission.feedback = payload.feedback
    submission.status = 'graded'
    audit(db, user, 'submission.graded', 'submission', submission.id)
    student = db.query(Student).filter(Student.id == submission.student_id).first()
    if student and student.user_id:
        db.add(Notification(user_id=student.user_id, kind='grade', title='Feedback is ready', body=f'Your work for {assignment.title} has been graded.', metadata_json={'submission_id': submission.id}))
    db.commit()
    db.refresh(submission)
    return submission


@app.get(f'{settings.api_v1_prefix}/llm/status')
def llm_status(user: CurrentTeacher) -> dict[str, Any]:
    provider = build_provider(settings)
    if hasattr(provider, 'get_health_status'):
        status = provider.get_health_status()
        return {
            'provider': status.get('provider', provider.provider_name),
            'base_url': status.get('base_url', settings.ollama_base_url),
            'model': status.get('model', settings.llm_model_name),
            'reachable': status.get('reachable', False),
            'model_available': status.get('model_available', False),
            **({'error': status.get('error')} if status.get('error') else {}),
        }
    return {
        'provider': provider.provider_name,
        'base_url': settings.ollama_base_url,
        'model': settings.llm_model_name,
        'reachable': False,
        'model_available': False,
        'error': 'No external LLM provider is configured; development fallback is active.',
    }


@app.get(f'{settings.api_v1_prefix}/interventions')
def list_interventions(user: CurrentTeacher, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    items = db.query(InterventionDraft).order_by(InterventionDraft.created_at.desc()).all()
    return [{'id': item.id, 'student_id': item.student_id, 'title': item.title, 'body': item.body, 'status': item.status, 'provider': item.evidence.get('provider'), 'evidence': item.evidence} for item in items]


@app.post(f'{settings.api_v1_prefix}/interventions/generate', status_code=201)
def generate_intervention(payload: InterventionGenerateRequest, user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    student = db.query(Student).filter(Student.id == payload.student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail='Student not found')
    features = student_features(student, db)
    try:
        prediction = predict_with_active_model(features, db)
        explanation = explain_with_active_model(features, db, target_class=prediction['risk_level'])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail='Train the risk model before generating evidence-based drafts.') from exc
    momentum_rows = db.query(AcademicMomentum).filter(AcademicMomentum.student_id == student.id).order_by(AcademicMomentum.observed_at).all()
    momentum_values: dict[str, list[float]] = {}
    for row in momentum_rows:
        momentum_values.setdefault(row.metric, []).append(row.value)
    momentum_status = {name: calculate_momentum(values)['classification'] for name, values in momentum_values.items()}
    retrieval = retrieve(f'{student.department or ""} academic support mentoring attendance assessment')
    resources = [{'title': item['source'], 'text': item['text']} for item in retrieval['sources']]
    shap_contributions = explanation.get('contributions', {})
    shap_values = explanation.get('feature_values', {})
    shap_evidence = [
        {
            'feature': name,
            'value': shap_values.get(name),
            'model_contribution': float(value),
        }
        for name, value in shap_contributions.items()
        if isinstance(value, (int, float))
    ]
    context = InterventionContext(
        student_name=student.full_name,
        risk_level=prediction['risk_level'],
        risk_probability=prediction['risk_probability'],
        class_probabilities=prediction['class_probabilities'],
        model_version=prediction['model_version'],
        shap_factors=explanation['summary'],
        shap_evidence=shap_evidence,
        momentum=momentum_status,
        attendance=student.attendance,
        assessment=student.assessment,
        assignment_engagement=student.assignments_completed,
        institutional_resources=resources,
        subject_academic_context={
            code: {key: value for key, value in record.items() if key not in {'name', 'import_batch_id'} and value is not None}
            for code, record in student_subject_records(student, db)['subjects'].items()
            if any(value is not None for key, value in record.items() if key not in {'name', 'import_batch_id'})
        },
        source_notice=retrieval['message'] or 'Use only the cited institutional resources.',
    )
    provider = build_provider(settings)
    try:
        body = provider.generate_intervention(context)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    validation_errors = validate_intervention_draft(body, context)
    if validation_errors:
        raise HTTPException(
            status_code=422,
            detail={
                'code': 'INTERVENTION_EVIDENCE_VALIDATION_FAILED',
                'message': 'The generated draft did not pass evidence validation. Regenerate or create a manual faculty draft.',
                'issues': validation_errors,
            },
        )
    student.risk_level = prediction['risk_level']
    student.risk_probability = prediction['risk_probability']
    db.add(RiskPrediction(student_id=student.id, risk_level=prediction['risk_level'], probability=prediction['risk_probability'], model_version=prediction['model_version'], prediction_timestamp=prediction['prediction_timestamp'], input_features=features))
    db.add(RiskSnapshot(student_id=student.id, risk_level=prediction['risk_level'], probability=prediction['risk_probability'], recorded_at=prediction['prediction_timestamp'].replace(tzinfo=None)))
    draft = InterventionDraft(student_id=student.id, title='Support check-in', body=body, status='draft', evidence={
        'risk_prediction': {
            **prediction,
            'prediction_timestamp': prediction['prediction_timestamp'].isoformat(),
        },
        'shap': explanation,
        'momentum': momentum_status,
        'rag': retrieval,
        'provider': provider.provider_name,
    })
    db.add(draft)
    audit(db, user, 'intervention.draft_generated', 'intervention_draft')
    db.commit()
    db.refresh(draft)
    return {'id': draft.id, 'student_id': draft.student_id, 'title': draft.title, 'body': draft.body, 'status': draft.status, 'provider': provider.provider_name, 'evidence': draft.evidence}


@app.patch(f'{settings.api_v1_prefix}/interventions/{{draft_id}}')
def edit_intervention(draft_id: int, payload: InterventionEditRequest, user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, Any]:
    draft = db.query(InterventionDraft).filter(InterventionDraft.id == draft_id, InterventionDraft.status == 'draft').first()
    if draft is None:
        raise HTTPException(status_code=404, detail='Draft not found')
    draft.title = payload.title
    disclaimer = 'AI-GENERATED DRAFT - FACULTY REVIEW REQUIRED'
    draft.body = payload.body if payload.body.startswith(disclaimer) else f'{disclaimer}\n{payload.body}'
    audit(db, user, 'intervention.draft_edited', 'intervention_draft', draft.id)
    db.commit()
    return {'id': draft.id, 'title': draft.title, 'body': draft.body, 'status': draft.status}


@app.post(f'{settings.api_v1_prefix}/interventions/{{draft_id}}/approve')
def approve_intervention(draft_id: int, user: CurrentTeacher, db: Session = Depends(get_db)) -> dict[str, str]:
    draft = db.query(InterventionDraft).filter(InterventionDraft.id == draft_id, InterventionDraft.status == 'draft').first()
    if draft is None:
        raise HTTPException(status_code=404, detail='Draft not found')
    teacher = db.query(Teacher).filter(Teacher.user_id == user.id).first()
    if teacher is None:
        teacher = Teacher(user_id=user.id)
        db.add(teacher)
        db.flush()
    intervention = Intervention(student_id=draft.student_id, teacher_id=teacher.id if teacher else None, title=draft.title, body=draft.body, status='sent', sent_at=datetime.utcnow())
    db.add(intervention)
    db.add(InterventionReview(draft_id=draft.id, teacher_id=teacher.id, decision='approved'))
    draft.status = 'approved'
    student = db.query(Student).filter(Student.id == draft.student_id).first()
    if student and student.user_id:
        db.add(Notification(user_id=student.user_id, kind='support', title=draft.title, body=draft.body, metadata_json={'intervention_id': intervention.id}))
    audit(db, user, 'intervention.approved', 'intervention', draft.id)
    db.commit()
    return {'status': 'approved'}


@app.get(f'{settings.api_v1_prefix}/knowledge/search')
def knowledge_search(query: str, user: CurrentUser, top_k: int = 4) -> dict[str, Any]:
    return retrieve(query, min(max(top_k, 1), 10))


@app.get(f'{settings.api_v1_prefix}/reports/export.csv')
def export_report(user: CurrentTeacher, db: Session = Depends(get_db), report_type: str = 'risk', academic_period: str | None = None) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    students = db.query(Student).order_by(Student.student_id).all()
    current_predictions = {student.id: student_risk_view(student, db)[1] for student in students} if report_type in {'risk', 'class'} else {}
    if report_type == 'risk':
        writer.writerow(['student_id', 'name', 'department', 'risk_level', 'risk_class_probability', 'attendance', 'assessment', 'current_gpa', 'momentum_signal'])
        for student in students:
            history = db.query(AcademicMomentum.value).filter(AcademicMomentum.student_id == student.id, AcademicMomentum.metric == 'assessment').order_by(AcademicMomentum.observed_at).all()
            prediction = current_predictions[student.id]
            features = student_features(student, db)
            writer.writerow([student.student_id, student.full_name, student.department, prediction['risk_level'], prediction['risk_probability'], features['attendance'], features['assessment'], student.current_gpa, calculate_momentum([row[0] for row in history])['classification']])
    elif report_type == 'class':
        writer.writerow(['metric', 'count'])
        writer.writerow(['students', len(students)])
        for level in ('HIGH', 'MEDIUM', 'LOW'):
            writer.writerow([f'risk_{level.lower()}', sum(prediction['risk_level'] == level for prediction in current_predictions.values())])
    elif report_type == 'assignments':
        writer.writerow(['assignment_id', 'title', 'course', 'status', 'assigned', 'submitted', 'pending', 'late', 'graded', 'due_date'])
        for assignment in db.query(Assignment).order_by(Assignment.id).all():
            counts = {'assigned': db.query(AssignmentStudent.id).filter(AssignmentStudent.assignment_id == assignment.id).count()}
            counts['submitted'] = db.query(Submission.id).filter(Submission.assignment_id == assignment.id, Submission.status.in_(['submitted', 'late', 'graded'])).count()
            counts['late'] = db.query(Submission.id).filter(Submission.assignment_id == assignment.id, Submission.status == 'late').count()
            counts['graded'] = db.query(Submission.id).filter(Submission.assignment_id == assignment.id, Submission.status == 'graded').count()
            writer.writerow([assignment.id, assignment.title, assignment.course, assignment.status, counts['assigned'], counts['submitted'], max(0, counts['assigned'] - counts['submitted']), counts['late'], counts['graded'], assignment.due_date.isoformat() if assignment.due_date else ''])
    elif report_type == 'internal_marks':
        try:
            period = selected_academic_period(db, academic_period)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        records = subject_records_by_student(db, [student.id for student in students], period)
        headers = ['Academic Period', 'USN', 'Student Name', 'Department', 'Section']
        for code in SUBJECTS:
            headers.extend([f'{code} FA1 /25', f'{code} FA2 /25', f'{code} Assignment /25', f'{code} Internal /50', f'{code} Attendance %'])
        headers.extend(['Total Internal /250', 'Average Internal /50'])
        writer.writerow(headers)
        for student in students:
            row_records = records.get(student.id, {})
            values: list[Any] = [period or '', student.student_id, student.full_name, student.department or '', student.section or '']
            for code in SUBJECTS:
                record = row_records.get(code)
                academic = serialize_record(record)
                values.extend([academic['fa1'] if academic['fa1'] is not None else '', academic['fa2'] if academic['fa2'] is not None else '', academic['assignment_mark'] if academic['assignment_mark'] is not None else '', academic['internal_mark'] if academic['internal_mark'] is not None else '', academic['attendance_rate'] if academic['attendance_rate'] is not None else ''])
            totals = academic_totals(row_records)
            values.extend([totals['total_internal'] if totals['total_internal'] is not None else '', totals['average_internal'] if totals['average_internal'] is not None else ''])
            writer.writerow(values)
    elif report_type == 'interventions':
        writer.writerow(['student_id', 'student_name', 'title', 'status', 'created_at', 'body'])
        for draft in db.query(InterventionDraft).order_by(InterventionDraft.created_at.desc()).all():
            student = db.query(Student).filter(Student.id == draft.student_id).first()
            writer.writerow([student.student_id if student else '', student.full_name if student else '', draft.title, draft.status, draft.created_at.isoformat(), draft.body])
    else:
        raise HTTPException(status_code=422, detail='Unsupported report type')
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="academic-{report_type}-report.csv"'})


@app.get(f'{settings.api_v1_prefix}/notifications')
def notifications(user: CurrentUser, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    items = db.query(Notification).filter(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(100).all()
    return [{'id': item.id, 'kind': item.kind, 'title': item.title, 'body': item.body, 'created_at': item.created_at.isoformat(), 'read': item.read_at is not None} for item in items]


@app.patch(f'{settings.api_v1_prefix}/notifications/{{notification_id}}/read')
def mark_notification_read(notification_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> dict[str, str]:
    item = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == user.id).first()
    if item is None:
        raise HTTPException(status_code=404, detail='Notification not found')
    item.read_at = datetime.utcnow()
    db.commit()
    return {'status': 'read'}