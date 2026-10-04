from pathlib import Path

import pandas as pd

FEATURES = [
    'attendance',
    'assessment',
    'previous_gpa',
    'current_gpa',
    'assignments_completed',
    'activity_per_week',
    'missing_submissions',
    'attendance_change',
    'assessment_change',
    'momentum_score',
]
FEATURE_CONTRACT_VERSION = 'risk-features-v1'
TARGET = 'risk_label'
FEATURE_CONTRACT = {
    'attendance': {'source': 'student_features imported attendance observations or Student.attendance', 'meaning': 'Imported attendance mean when present, otherwise legacy profile rate.', 'scope': 'global', 'model_input': True},
    'assessment': {'source': 'student_features imported assessment observations or Student.assessment', 'meaning': 'Imported assessment mean when present, otherwise legacy profile value.', 'scope': 'global', 'model_input': True},
    'previous_gpa': {'source': 'Student.previous_gpa', 'meaning': 'Previous cumulative GPA.', 'scope': 'global', 'model_input': True},
    'current_gpa': {'source': 'Student.current_gpa', 'meaning': 'Current cumulative GPA.', 'scope': 'global', 'model_input': True},
    'assignments_completed': {'source': 'Student.assignments_completed', 'meaning': 'Existing profile engagement value.', 'scope': 'global', 'model_input': True},
    'activity_per_week': {'source': 'latest four AcademicMomentum(activity) values', 'meaning': 'Mean quantity of the four latest dated activity observations.', 'scope': 'global', 'model_input': True},
    'missing_submissions': {'source': 'AssignmentStudent and Submission', 'meaning': 'Maximum of all enrollment count minus submitted/late/graded submissions and zero.', 'scope': 'global', 'model_input': True},
    'attendance_change': {'source': 'AcademicMomentum(attendance)', 'meaning': 'Momentum percent change over dated attendance observations; zero when unavailable.', 'scope': 'global', 'model_input': True},
    'assessment_change': {'source': 'AcademicMomentum(assessment)', 'meaning': 'Momentum percent change over dated assessment observations; zero when unavailable.', 'scope': 'global', 'model_input': True},
    'momentum_score': {'source': 'AcademicMomentum attendance and assessment trends', 'meaning': 'Mean available trend slope across attendance and assessment.', 'scope': 'global', 'model_input': True},
    'fa1': {'source': 'StudentSubjectAcademicRecord.fa1', 'meaning': 'Subject-specific formative assessment 1 mark out of 25.', 'scope': 'subject', 'model_input': False},
    'fa2': {'source': 'StudentSubjectAcademicRecord.fa2', 'meaning': 'Subject-specific formative assessment 2 mark out of 25.', 'scope': 'subject', 'model_input': False},
}


def load_training_data(path: Path) -> tuple[pd.DataFrame, pd.Series]:
    data = pd.read_csv(path)
    missing = sorted(set(FEATURES + [TARGET]) - set(data.columns))
    if missing:
        raise ValueError(f'Dataset is missing required columns: {", ".join(missing)}')
    if {'risk_level', 'risk_probability', 'student_id'} & set(FEATURES):
        raise ValueError('Leakage-prone identity and target proxies cannot be model features')
    features = data[FEATURES].apply(pd.to_numeric, errors='coerce')
    labels = data[TARGET].astype(str).str.upper()
    if labels.nunique() < 2:
        raise ValueError('Training data must include at least two risk classes')
    if features.dropna(how='all').empty:
        raise ValueError('Training features contain no numeric observations')
    return features, labels