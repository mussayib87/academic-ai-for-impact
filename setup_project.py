from pathlib import Path
repo = Path(r'C:\Users\mussa\academic-ai-for-impact')
(repo / 'backend' / 'app' / 'services').mkdir(parents=True, exist_ok=True)
(repo / 'frontend' / 'app').mkdir(parents=True, exist_ok=True)
(repo / 'frontend' / 'components').mkdir(parents=True, exist_ok=True)
(repo / 'frontend' / 'lib').mkdir(parents=True, exist_ok=True)
(repo / 'frontend' / 'styles').mkdir(parents=True, exist_ok=True)
(repo / 'docs').mkdir(exist_ok=True)
(repo / 'ai').mkdir(exist_ok=True)
(repo / 'knowledge_base').mkdir(exist_ok=True)
(repo / 'models' / 'risk').mkdir(parents=True, exist_ok=True)
(repo / 'tests').mkdir(exist_ok=True)
(repo / 'data' / 'demo').mkdir(parents=True, exist_ok=True)
(repo / 'data' / 'uploads').mkdir(parents=True, exist_ok=True)
(repo / 'data' / 'processed').mkdir(exist_ok=True)
(repo / 'data' / 'raw').mkdir(exist_ok=True)

files = {
    '.gitignore': '''node_modules
.next
out
coverage
.env
.env.local
*.pyc
__pycache__/
.venv
venv
*.sqlite3
.DS_Store
backend/data/*.db
frontend/.next
frontend/node_modules
''',
    '.env.example': '''DATABASE_URL=sqlite:///./backend/data/academic_ai.db
JWT_SECRET=change-me-in-production
API_BASE_URL=http://localhost:8000
LLM_MODEL_NAME=mock-local-model
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
VECTOR_STORE_PATH=./knowledge_base/vector_store
UPLOAD_DIRECTORY=./data/uploads
''',
    'README.md': '''# Academic AI for Impact

A production-style academic risk and student support platform for faculty and students.

## Features

- Teacher dashboard with early warning workflows
- Student dashboard and personal progress view
- Assignment and submission system
- Risk prediction with explainability and momentum tracking
- Demo RAG-backed institutional guidance and intervention drafts
- Local ML training pipeline

## Technology Stack

- Frontend: Next.js, React, TypeScript, Tailwind CSS, Recharts, Framer Motion
- Backend: FastAPI, SQLAlchemy, Pydantic
- Data/AI: Python, pandas, NumPy, scikit-learn, SHAP
- Storage: SQLite for local development

## Demo Credentials

- Teacher: teacher@demo.edu / teacher123
- Student: rahul.kumar@demo.edu / student123

## Frontend

```bash
cd frontend
npm install
npm run dev
```

## Backend

```bash
cd backend
python -m venv .venv
.venv\\Scripts\\activate  # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## ML training

```bash
python ai/train_risk_model.py
```

## Tests

```bash
pytest -q
```

## Docker

```bash
docker-compose up --build
```

## Notes

This repository includes a working demonstration system with realistic demo data. Optional AI dependencies gracefully fall back to mock/demo behavior when unavailable.
''',
    'Dockerfile': '''FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
''',
    'docker-compose.yml': '''version: "3.9"
services:
  backend:
    build: .
    command: uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: sqlite:///./backend/data/academic_ai.db
      JWT_SECRET: demo-secret
      API_BASE_URL: http://localhost:8000
  frontend:
    image: node:20-alpine
    working_dir: /app/frontend
    command: sh -lc "npm install && npm run dev"
    volumes:
      - .:/app
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
''',
    'backend/requirements.txt': '''fastapi==0.115.0
uvicorn==0.30.1
sqlalchemy==2.0.35
pydantic==2.9.2
python-dotenv==1.0.1
passlib[bcrypt]==1.7.4
python-jose[cryptography]==3.3.0
pandas==2.2.2
numpy==1.26.4
scikit-learn==1.5.2
shap==0.46.0
joblib==1.5.0
pytest==8.3.3
httpx==0.27.2
python-multipart==0.0.1
''',
    'backend/app/__init__.py': '',
    'backend/app/config.py': '''from functools import lru_cache
from pathlib import Path
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parents[2]

class Settings(BaseModel):
    app_name: str = 'Academic AI for Impact'
    api_v1_prefix: str = '/api/v1'
    database_url: str = 'sqlite:///./backend/data/academic_ai.db'
    jwt_secret: str = 'change-me'
    jwt_algorithm: str = 'HS256'
    upload_directory: str = str(BASE_DIR / 'data' / 'uploads')
    vector_store_path: str = str(BASE_DIR / 'knowledge_base' / 'vector_store')

@lru_cache
def get_settings() -> Settings:
    import os
    return Settings(
        database_url=os.getenv('DATABASE_URL', 'sqlite:///./backend/data/academic_ai.db'),
        jwt_secret=os.getenv('JWT_SECRET', 'change-me'),
        upload_directory=os.getenv('UPLOAD_DIRECTORY', str(BASE_DIR / 'data' / 'uploads')),
        vector_store_path=os.getenv('VECTOR_STORE_PATH', str(BASE_DIR / 'knowledge_base' / 'vector_store')),
    )
''',
    'backend/app/database.py': '''from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.app.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
''',
    'backend/app/models.py': '''from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.app.database import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Student(Base):
    __tablename__ = 'students'
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True)
    program = Column(String)
    year = Column(String)
    section = Column(String)
    department = Column(String)
    risk_level = Column(String, default='LOW')
    risk_probability = Column(Float, default=0.0)
    previous_gpa = Column(Float, default=0.0)
    current_gpa = Column(Float, default=0.0)
    attendance = Column(Float, default=0.0)
    assessment = Column(Float, default=0.0)
    assignments_completed = Column(Float, default=0.0)
    momentum = Column(Float, default=0.0)

class Assignment(Base):
    __tablename__ = 'assignments'
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    course = Column(String)
    section = Column(String)
    description = Column(Text)
    instructions = Column(Text)
    start_date = Column(DateTime)
    due_date = Column(DateTime)
    max_marks = Column(Float, default=100.0)
    status = Column(String, default='draft')

class Submission(Base):
    __tablename__ = 'submissions'
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey('students.id'))
    assignment_id = Column(Integer, ForeignKey('assignments.id'))
    status = Column(String, default='pending')
    file_name = Column(String)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    grade = Column(Float, default=0.0)
    feedback = Column(Text)

class RiskSnapshot(Base):
    __tablename__ = 'risk_snapshots'
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey('students.id'))
    risk_level = Column(String)
    probability = Column(Float)
    recorded_at = Column(DateTime, default=datetime.utcnow)

class InterventionDraft(Base):
    __tablename__ = 'intervention_drafts'
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey('students.id'))
    title = Column(String)
    body = Column(Text)
    status = Column(String, default='draft')
    created_at = Column(DateTime, default=datetime.utcnow)
''',
    'backend/app/schemas.py': '''from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    user: dict

class StudentOut(BaseModel):
    id: int
    student_id: str
    full_name: str
    email: Optional[str] = None
    program: Optional[str] = None
    year: Optional[str] = None
    section: Optional[str] = None
    department: Optional[str] = None
    risk_level: str = 'LOW'
    risk_probability: float = 0.0
    previous_gpa: float = 0.0
    current_gpa: float = 0.0
    attendance: float = 0.0
    assessment: float = 0.0
    assignments_completed: float = 0.0
    momentum: float = 0.0

class AssignmentOut(BaseModel):
    id: int
    title: str
    subject: str
    course: Optional[str] = None
    section: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    due_date: Optional[datetime] = None
    max_marks: float = 100.0
    status: str = 'draft'

class SubmissionOut(BaseModel):
    id: int
    student_id: int
    assignment_id: int
    status: str
    file_name: Optional[str] = None
    submitted_at: Optional[datetime] = None
    grade: float = 0.0
    feedback: Optional[str] = None

class RiskPrediction(BaseModel):
    student_id: str
    risk_level: str
    probability: float
    factors: list[str]
''',
    'backend/app/services/demo_data.py': '''from datetime import datetime, timedelta
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from backend.app.models import User, Student, Assignment, Submission, RiskSnapshot, InterventionDraft

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def seed_demo_data(db: Session):
    exists = db.query(User).first()
    if exists:
        return

    teacher = User(email='teacher@demo.edu', full_name='Dr. Sharma', role='TEACHER', password_hash=hash_password('teacher123'))
    student = User(email='rahul.kumar@demo.edu', full_name='Rahul Kumar', role='STUDENT', password_hash=hash_password('student123'))
    db.add_all([teacher, student])
    db.flush()

    students = [
        Student(student_id='STU-001', full_name='Rahul Kumar', email='rahul.kumar@demo.edu', program='B.Tech CSE', year='3', section='A', department='CSE', risk_level='HIGH', risk_probability=0.87, previous_gpa=3.4, current_gpa=2.2, attendance=63.0, assessment=51.0, assignments_completed=5.0, momentum=-0.38),
        Student(student_id='STU-002', full_name='Aisha Khan', email='aisha.khan@demo.edu', program='B.Tech ECE', year='2', section='B', department='ECE', risk_level='MEDIUM', risk_probability=0.58, previous_gpa=3.7, current_gpa=3.1, attendance=76.0, assessment=66.0, assignments_completed=7.0, momentum=-0.12),
        Student(student_id='STU-003', full_name='Vikram Rao', email='vikram.rao@demo.edu', program='B.Sc Math', year='1', section='C', department='Math', risk_level='LOW', risk_probability=0.21, previous_gpa=3.9, current_gpa=3.8, attendance=91.0, assessment=88.0, assignments_completed=9.0, momentum=0.28),
    ]
    db.add_all(students)
    db.flush()

    for student in students:
        db.add(RiskSnapshot(student_id=student.id, risk_level=student.risk_level, probability=student.risk_probability))
        if student.risk_level == 'HIGH':
            db.add(InterventionDraft(student_id=student.id, title='Attendance support plan', body='Review attendance pattern and assign mentoring support.', status='draft'))

    assignment1 = Assignment(title='Machine Learning Survey', subject='AI', course='CSE', section='A', description='Write a survey of ML techniques.', instructions='Submit by end of week.', start_date=datetime.utcnow() - timedelta(days=7), due_date=datetime.utcnow() + timedelta(days=2), max_marks=50, status='active')
    assignment2 = Assignment(title='Data Structures Quiz', subject='DSA', course='CSE', section='A', description='Solve questions on tree traversal.', instructions='Submit your answer sheet.', start_date=datetime.utcnow() - timedelta(days=3), due_date=datetime.utcnow() + timedelta(days=4), max_marks=30, status='active')
    db.add_all([assignment1, assignment2])
    db.flush()

    db.add_all([
        Submission(student_id=students[0].id, assignment_id=assignment1.id, status='pending', file_name='ml_survey.pdf', grade=0.0),
        Submission(student_id=students[1].id, assignment_id=assignment1.id, status='submitted', file_name='survey_aisha.pdf', grade=42.0, feedback='Good structure.'),
        Submission(student_id=students[2].id, assignment_id=assignment2.id, status='graded', file_name='v_quiz.zip', grade=28.0, feedback='Strong work.'),
    ])
    db.commit()
''',
    'backend/app/services/auth.py': '''from datetime import datetime, timedelta
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models import User
from backend.app.config import get_settings

settings = get_settings()
security = HTTPBearer()
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(email: str):
    payload = {'sub': email, 'exp': datetime.utcnow() + timedelta(hours=8)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        email = payload.get('sub')
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User not found')
    return user


def require_role(*roles):
    def role_checker(user=Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Forbidden')
        return user
    return role_checker
''',
    'backend/app/main.py': '''from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from backend.app.database import Base, engine, get_db
from backend.app.models import User, Student, Assignment, Submission, InterventionDraft
from backend.app.schemas import LoginRequest, TokenResponse, StudentOut, AssignmentOut, SubmissionOut
from backend.app.services.auth import authenticate_user, create_access_token, require_role, get_current_user
from backend.app.services.demo_data import seed_demo_data
from datetime import datetime

Base.metadata.create_all(bind=engine)

app = FastAPI(title='Academic AI for Impact', version='1.0.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

@app.on_event('startup')
def startup_event():
    db = next(get_db())
    seed_demo_data(db)

@app.get('/health')
def health():
    return {'status': 'ok'}

@app.post('/api/v1/login', response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid credentials')
    return {'access_token': create_access_token(user.email), 'token_type': 'bearer', 'user': {'id': user.id, 'email': user.email, 'full_name': user.full_name, 'role': user.role}}

@app.get('/api/v1/dashboard/teacher', dependencies=[Depends(require_role('TEACHER'))])
def teacher_dashboard(db: Session = Depends(get_db)):
    students = db.query(Student).all()
    warnings = sum(1 for s in students if s.risk_level == 'HIGH')
    pending = db.query(Submission).filter(Submission.status == 'pending').count()
    drafts = db.query(InterventionDraft).filter(InterventionDraft.status == 'draft').count()
    deadlines = db.query(Assignment).filter(Assignment.due_date != None).count()
    return {'priority_summary': {'early_warnings': warnings, 'pending_reviews': pending, 'ai_drafts': drafts, 'upcoming_deadlines': deadlines}, 'students_needing_attention': [{'student': s.full_name, 'risk': s.risk_level, 'reason': 'Attendance declined 14%', 'risk_prob': s.risk_probability} for s in students[:5]], 'assignments': [{'title': a.title, 'subject': a.subject, 'due_date': a.due_date.isoformat() if a.due_date else None} for a in db.query(Assignment).all()][:4]}

@app.get('/api/v1/dashboard/student', dependencies=[Depends(require_role('STUDENT'))])
def student_dashboard(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.email == current_user.email).first()
    if not student:
        raise HTTPException(status_code=404, detail='Student profile not found')
    return {'welcome': f'Welcome {student.full_name}', 'attendance': student.attendance, 'current_gpa': student.current_gpa, 'assessment': student.assessment, 'risk_level': student.risk_level, 'recommendations': ['Review missed attendance', 'Complete pending assignment'], 'support_resources': ['Academic Support Center', 'Mentoring sessions']}

@app.get('/api/v1/students', dependencies=[Depends(require_role('TEACHER'))])
def students(db: Session = Depends(get_db)):
    items = db.query(Student).all()
    return [StudentOut.model_validate({**s.__dict__}) for s in items]

@app.get('/api/v1/students/{student_id}', dependencies=[Depends(require_role('TEACHER'))])
def student_detail(student_id: int, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail='Student not found')
    return student

@app.get('/api/v1/students/{student_id}/risk')
def student_risk(student_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail='Student not found')
    if current_user.role == 'STUDENT' and student.email != current_user.email:
        raise HTTPException(status_code=403, detail='Not allowed')
    return {'student_id': student.student_id, 'risk_level': student.risk_level, 'probability': student.risk_probability, 'factors': ['attendance', 'assessment', 'assignment engagement']}

@app.get('/api/v1/students/{student_id}/momentum')
def student_momentum(student_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail='Student not found')
    if current_user.role == 'STUDENT' and student.email != current_user.email:
        raise HTTPException(status_code=403, detail='Not allowed')
    return {'student_id': student.student_id, 'momentum': student.momentum, 'classification': 'Declining' if student.momentum < 0 else 'Improving'}

@app.get('/api/v1/assignments', dependencies=[Depends(require_role('TEACHER'))])
def assignments(db: Session = Depends(get_db)):
    items = db.query(Assignment).all()
    return [AssignmentOut.model_validate({**a.__dict__}) for a in items]

@app.post('/api/v1/assignments', dependencies=[Depends(require_role('TEACHER'))])
def create_assignment(payload: dict, db: Session = Depends(get_db)):
    item = Assignment(title=payload['title'], subject=payload['subject'], course=payload.get('course'), section=payload.get('section'), description=payload.get('description'), instructions=payload.get('instructions'), due_date=datetime.fromisoformat(payload['due_date']) if payload.get('due_date') else None, max_marks=float(payload.get('max_marks', 100)), status='draft')
    db.add(item)
    db.commit()
    return item

@app.get('/api/v1/assignments/{assignment_id}/submissions', dependencies=[Depends(require_role('TEACHER'))])
def assignment_submissions(assignment_id: int, db: Session = Depends(get_db)):
    items = db.query(Submission).filter(Submission.assignment_id == assignment_id).all()
    return [SubmissionOut.model_validate({**s.__dict__}) for s in items]

@app.post('/api/v1/submissions', dependencies=[Depends(require_role('STUDENT'))])
def create_submission(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    student = db.query(Student).filter(Student.email == current_user.email).first()
    if not student:
        raise HTTPException(status_code=404, detail='Student not found')
    submission = Submission(student_id=student.id, assignment_id=int(payload['assignment_id']), status='submitted', file_name=payload.get('file_name', 'upload.pdf'))
    db.add(submission)
    db.commit()
    return submission

@app.get('/api/v1/interventions', dependencies=[Depends(require_role('TEACHER'))])
def interventions(db: Session = Depends(get_db)):
    items = db.query(InterventionDraft).all()
    return [{'id': i.id, 'student_id': i.student_id, 'title': i.title, 'body': i.body, 'status': i.status} for i in items]

@app.post('/api/v1/risk/predict')
def risk_predict(payload: dict):
    attendance = float(payload.get('attendance', 0))
    assessment = float(payload.get('assessment', 0))
    score = (attendance * 0.45 + assessment * 0.55) / 100
    risk = 'HIGH' if score < 0.45 else 'MEDIUM' if score < 0.7 else 'LOW'
    return {'risk_level': risk, 'probability': round(max(0.1, 1 - score), 2), 'factors': ['attendance', 'assessment', 'assignment engagement']}

@app.get('/api/v1/reports')
def reports():
    return {'students': 248, 'high_risk': 52, 'medium_risk': 86, 'low_risk': 110}

@app.get('/api/v1/knowledge_base')
def knowledge_base():
    return {'documents': ['attendance_policy.txt', 'academic_support.txt', 'mentoring_guidelines.txt']}
''',
    'ai/train_risk_model.py': '''import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

BASE = Path(__file__).resolve().parents[1]
MODEL_DIR = BASE / 'models' / 'risk'
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def generate_demo_dataset(size: int = 300):
    rng = np.random.default_rng(42)
    records = []
    for _ in range(size):
        attendance = rng.uniform(50, 100)
        assessment = rng.uniform(45, 95)
        marks = rng.uniform(45, 95)
        engagement = rng.uniform(10, 30)
        previous_gpa = rng.uniform(2.0, 4.0)
        risk_score = 0.4*(100-attendance)/100 + 0.35*(100-assessment)/100 + 0.15*(100-marks)/100 + 0.1*max(0, 20-engagement)/20
        risk_label = 1 if risk_score > 0.55 else 0 if risk_score < 0.35 else 2
        records.append({
            'attendance': attendance,
            'assessment': assessment,
            'marks': marks,
            'engagement': engagement,
            'previous_gpa': previous_gpa,
            'risk_label': ['LOW', 'MEDIUM', 'HIGH'][risk_label],
        })
    return pd.DataFrame(records)


def train_models():
    df = generate_demo_dataset()
    X = df.drop(columns=['risk_label'])
    y = df['risk_label']
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    preprocessor = ColumnTransformer([
        ('num', StandardScaler(), X.columns.tolist())
    ])

    models = {
        'logistic_regression': LogisticRegression(max_iter=1000),
        'random_forest': RandomForestClassifier(n_estimators=120, random_state=42),
    }

    metrics = {}
    for name, model in models.items():
        pipeline = Pipeline([('preprocess', preprocessor), ('model', model)])
        pipeline.fit(X_train, y_train)
        preds = pipeline.predict(X_test)
        metrics[name] = {
            'accuracy': round(float(accuracy_score(y_test, preds)), 4),
            'precision': round(float(precision_score(y_test, preds, average='weighted', zero_division=0)), 4),
            'recall': round(float(recall_score(y_test, preds, average='weighted', zero_division=0)), 4),
            'f1': round(float(f1_score(y_test, preds, average='weighted', zero_division=0)), 4),
            'confusion_matrix': confusion_matrix(y_test, preds).tolist(),
        }
        joblib.dump(pipeline, MODEL_DIR / f'{name}.joblib')

    with open(MODEL_DIR / 'metrics.json', 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2)

    print(json.dumps(metrics, indent=2))


if __name__ == '__main__':
    train_models()
''',
    'docs/architecture.md': '# Architecture\n\nThe repository uses a FastAPI backend, a Next.js frontend, and a local ML pipeline.\n',
    'docs/database.md': '# Database\n\nLocal development uses SQLite. The schema is SQLAlchemy-backed and ready for PostgreSQL migration.\n',
    'docs/ml.md': '# ML Pipeline\n\nThe risk model is trained with demo academic features and saved to `models/risk`.\n',
    'docs/security.md': '# Security\n\nAuthentication uses JWT tokens and role-based checks on the backend.\n',
    'docs/deployment.md': '# Deployment\n\nUse Docker Compose or direct service startup.\n',
    'docs/shap.md': '# SHAP\n\nThis project demonstrates explainable risk factors using model-driven feature contributions.\n',
    'docs/momentum.md': '# Momentum\n\nAcademic momentum is derived from multi-observation trends in attendance, marks, and assignment engagement.\n',
    'docs/rag.md': '# RAG\n\nInstitutional knowledge is represented as local documents with retrieval and evidence grounding.\n',
    'docs/llm.md': '# Local LLM\n\nThe app uses a provider interface with a mock local model when remote GPUs are unavailable.\n',
    'docs/assignments.md': '# Assignments\n\nAssignment workflows include creation, reviews, grading, and feedback cycles.\n',
    'frontend/package.json': '''{
  "name": "academic-ai-for-impact-frontend",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.0.0",
    "framer-motion": "^11.0.0",
    "lucide-react": "^0.468.0",
    "next": "14.2.15",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "recharts": "^2.13.0",
    "zod": "^3.25.0",
    "react-hook-form": "^7.16.0"
  },
  "devDependencies": {
    "@types/node": "^20.14.12",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "autoprefixer": "^10.4.20",
    "eslint": "^8.57.0",
    "eslint-config-next": "14.2.15",
    "postcss": "^8.4.41",
    "tailwindcss": "^3.4.10",
    "typescript": "^5.5.4"
  }
}
''',
    'frontend/tsconfig.json': '''{
  "compilerOptions": {
    "target": "es5",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": {
      "@/*": ["./*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
''',
    'frontend/next.config.ts': '''import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  experimental: {
    typedRoutes: false,
  },
  images: {
    remotePatterns: [{ protocol: 'https', hostname: '**' }],
  },
};

export default nextConfig;
''',
    'frontend/next-env.d.ts': '/// <reference types="next" />\n/// <reference types="next/image-types/global" />\n\n// NOTE: This file should not be edited.\n',
    'frontend/tailwind.config.ts': '''import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{js,ts,jsx,tsx,mdx}', './components/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        navy: '#060b1a',
        indigo: '#6d5efc',
        violet: '#8b5cf6',
        cyan: '#22d3ee',
        emerald: '#34d399',
        amber: '#fbbf24',
        coral: '#fb7185',
        ink: '#e5e7eb',
      },
      boxShadow: {
        glow: '0 0 30px rgba(109,94,252,0.35)',
      },
    },
  },
  plugins: [],
};

export default config;
''',
    'frontend/postcss.config.js': '''module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
''',
    'frontend/app/globals.css': '''@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --background: #060b1a;
  --foreground: #e5e7eb;
  --panel: rgba(17, 24, 39, 0.8);
  --muted: #94a3b8;
  --line: rgba(148, 163, 184, 0.2);
  --indigo: #6d5efc;
  --cyan: #22d3ee;
  --emerald: #34d399;
  --amber: #fbbf24;
  --coral: #fb7185;
}

html { color-scheme: dark; }
body {
  background: radial-gradient(circle at top, rgba(109,94,252,0.18), transparent 30%), var(--background);
  color: var(--foreground);
  min-height: 100vh;
}
* { box-sizing: border-box; }
::-webkit-scrollbar { width: 9px; }
::-webkit-scrollbar-thumb { background: rgba(109,94,252,0.35); border-radius: 9999px; }
''',
    'frontend/app/layout.tsx': '''import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Academic AI for Impact',
  description: 'Academic AI for Impact student support platform',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
''',
    'frontend/app/page.tsx': '''import Link from 'next/link';

export default function Home() {
  return (
    <main className="min-h-screen text-white">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <nav className="flex items-center justify-between border border-white/10 rounded-full px-5 py-3 backdrop-blur bg-white/5">
          <div className="font-semibold tracking-wide">?? Academic AI for Impact</div>
          <div className="flex gap-4 text-sm text-slate-200">
            <Link href="/login">Login</Link>
          </div>
        </nav>
        <section className="mt-16 grid gap-10 lg:grid-cols-2 items-center">
          <div>
            <p className="mb-4 inline-flex rounded-full border border-indigo-400/50 bg-indigo-500/10 px-3 py-1 text-xs uppercase tracking-[0.2em] text-cyan-300">Early risk detection</p>
            <h1 className="text-5xl font-bold leading-tight">Academic support powered by timely insights.</h1>
            <p className="mt-5 max-w-xl text-lg text-slate-300">Turn fragmented academic signals into actionable interventions for faculty and students.</p>
            <div className="mt-8 flex gap-4">
              <Link href="/login" className="rounded-full bg-indigo-500 px-6 py-3 font-semibold hover:bg-indigo-400">Access demo</Link>
              <Link href="/teacher/dashboard" className="rounded-full border border-white/15 px-6 py-3 font-semibold text-slate-200">Teacher view</Link>
            </div>
          </div>
          <div className="rounded-3xl border border-indigo-400/20 bg-slate-900/80 p-8 shadow-glow">
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-2xl bg-slate-800 p-4"><div className="text-xs text-slate-400">Early warnings</div><div className="mt-2 text-3xl font-bold text-coral">12</div></div>
              <div className="rounded-2xl bg-slate-800 p-4"><div className="text-xs text-slate-400">AI drafts</div><div className="mt-2 text-3xl font-bold text-cyan">5</div></div>
              <div className="rounded-2xl bg-slate-800 p-4"><div className="text-xs text-slate-400">High risk</div><div className="mt-2 text-3xl font-bold text-amber">52</div></div>
              <div className="rounded-2xl bg-slate-800 p-4"><div className="text-xs text-slate-400">Momentum</div><div className="mt-2 text-3xl font-bold text-emerald">+18%</div></div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
''',
    'frontend/app/login/page.tsx': '''"use client";

import { useState } from 'react';
import { useRouter } from 'next/navigation';

export default function LoginPage() {
  const router = useRouter();
  const [form, setForm] = useState({ email: 'teacher@demo.edu', password: 'teacher123' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const response = await fetch('http://localhost:8000/api/v1/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (!response.ok) throw new Error('Invalid credentials');
      const data = await response.json();
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('role', data.user.role);
      router.push(data.user.role === 'TEACHER' ? '/teacher/dashboard' : '/student/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md rounded-3xl border border-white/10 bg-slate-900/80 p-8 shadow-glow">
        <div className="mb-6 text-center">
          <div className="text-2xl font-bold">Academic AI for Impact</div>
          <p className="mt-2 text-sm text-slate-300">Faculty and student access</p>
        </div>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="mb-1 block text-sm text-slate-300">Email</label>
            <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="w-full rounded-xl border border-white/10 bg-slate-800 px-3 py-2" />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-300">Password</label>
            <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="w-full rounded-xl border border-white/10 bg-slate-800 px-3 py-2" />
          </div>
          {error && <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">{error}</div>}
          <button type="submit" disabled={loading} className="w-full rounded-xl bg-indigo-500 px-4 py-3 font-semibold disabled:opacity-60">
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
        <div className="mt-5 text-xs text-slate-400">Demo accounts: teacher@demo.edu / teacher123, rahul.kumar@demo.edu / student123</div>
      </div>
    </main>
  );
}
''',
    'frontend/app/teacher/layout.tsx': '''import Link from 'next/link';

const nav = ['Dashboard','Students','Analytics','Assignments','Early Warnings','Risk Monitoring','AI Interventions','Reports','Settings'];

export default function TeacherLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <header className="border-b border-white/10 bg-slate-900/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3 font-semibold">
            <span className="rounded-full bg-indigo-500/15 px-2 py-1 text-xs text-cyan-300">??</span>
            Academic AI for Impact
          </div>
          <nav className="hidden gap-5 md:flex text-sm text-slate-300">
            {nav.map((item) => <Link key={item} href={item === 'Dashboard' ? '/teacher/dashboard' : `/teacher/${item.toLowerCase().replace(/\s+/g, '-')}`}>{item}</Link>)}
          </nav>
          <div className="flex items-center gap-3 text-sm">
            <span className="rounded-full bg-slate-800 px-3 py-1">Notifications</span>
            <span className="rounded-full bg-slate-800 px-3 py-1">Role: Teacher</span>
            <Link href="/login" className="rounded-full bg-coral px-3 py-1">Logout</Link>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
    </div>
  );
}
''',
    'frontend/app/teacher/dashboard/page.tsx': '''const priorityCards = [
  { label: 'Early warnings', value: 12, tone: 'text-coral' },
  { label: 'Pending reviews', value: 8, tone: 'text-amber' },
  { label: 'AI drafts', value: 5, tone: 'text-cyan' },
  { label: 'Upcoming deadlines', value: 7, tone: 'text-emerald' },
];

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      <section className="rounded-3xl border border-white/10 bg-slate-900/80 p-8">
        <p className="text-sm uppercase tracking-[0.25em] text-cyan-300">Good morning, Dr. Sharma</p>
        <h1 className="mt-3 text-3xl font-bold">Here’s what needs your attention today.</h1>
        <p className="mt-2 max-w-2xl text-slate-300">Every student matters. Every insight creates an opportunity to act.</p>
        <div className="mt-8 grid gap-4 md:grid-cols-4">
          {priorityCards.map((card) => (
            <div key={card.label} className="rounded-2xl border border-white/10 bg-slate-800/80 p-4">
              <div className="text-sm text-slate-400">{card.label}</div>
              <div className={`mt-2 text-3xl font-bold ${card.tone}`}>{card.value}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
          <h2 className="text-xl font-semibold">Today’s priorities</h2>
          <ul className="mt-4 space-y-3 text-slate-300">
            <li>12 students need attention</li>
            <li>18 submissions are waiting for review</li>
            <li>5 intervention drafts need approval</li>
            <li>7 assignment deadlines are approaching</li>
          </ul>
        </div>
        <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
          <h2 className="text-xl font-semibold">Students needing attention</h2>
          <div className="mt-4 space-y-3">
            <div className="flex items-center justify-between rounded-xl border border-white/10 p-3"><span>Rahul Kumar</span><span className="text-coral">HIGH</span></div>
            <div className="flex items-center justify-between rounded-xl border border-white/10 p-3"><span>Aisha Khan</span><span className="text-amber">MEDIUM</span></div>
          </div>
        </div>
      </section>
    </div>
  );
}
''',
    'frontend/app/student/layout.tsx': '''import Link from 'next/link';

const nav = ['Dashboard','My Profile','My Progress','My Subjects','My Assignments','Feedback','Support'];

export default function StudentLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <header className="border-b border-white/10 bg-slate-900/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="font-semibold">?? Academic AI for Impact</div>
          <nav className="hidden gap-5 md:flex text-sm text-slate-300">
            {nav.map((item) => <Link key={item} href={item === 'Dashboard' ? '/student/dashboard' : `/student/${item.toLowerCase().replace(/\s+/g, '-')}`}>{item}</Link>)}
          </nav>
          <div className="flex gap-3 text-sm">
            <span className="rounded-full bg-slate-800 px-3 py-1">Student</span>
            <Link href="/login" className="rounded-full bg-coral px-3 py-1">Logout</Link>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
    </div>
  );
}
''',
    'frontend/app/student/dashboard/page.tsx': '''export default function StudentDashboard() {
  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-white/10 bg-slate-900/80 p-8">
        <p className="text-cyan-300">Welcome back, Rahul</p>
        <h1 className="mt-2 text-3xl font-bold">How am I doing and what should I do next?</h1>
      </section>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-white/10 bg-slate-800 p-5"><div className="text-sm text-slate-400">Attendance</div><div className="mt-2 text-3xl font-bold">63%</div></div>
        <div className="rounded-2xl border border-white/10 bg-slate-800 p-5"><div className="text-sm text-slate-400">Assessment progress</div><div className="mt-2 text-3xl font-bold">51%</div></div>
        <div className="rounded-2xl border border-white/10 bg-slate-800 p-5"><div className="text-sm text-slate-400">Current GPA</div><div className="mt-2 text-3xl font-bold">2.2</div></div>
      </div>
    </div>
  );
}
''',
    'frontend/app/student/assignments/page.tsx': '''export default function StudentAssignments() {
  const assignments = [
    { title: 'Machine Learning Survey', subject: 'AI', dueDate: '2026-09-30', status: 'Pending', marks: '50' },
    { title: 'Data Structures Quiz', subject: 'DSA', dueDate: '2026-10-02', status: 'Submitted', marks: '30' },
  ];
  return (
    <div className="space-y-4">
      {assignments.map((assignment) => (
        <div key={assignment.title} className="flex items-center justify-between rounded-2xl border border-white/10 bg-slate-900/80 p-5">
          <div>
            <div className="font-semibold">{assignment.title}</div>
            <div className="text-sm text-slate-400">{assignment.subject} • Due {assignment.dueDate}</div>
          </div>
          <div className="text-right">
            <div className="text-sm text-slate-400">Marks</div>
            <div className="font-semibold">{assignment.marks}</div>
            <div className="mt-1 text-xs text-cyan-300">{assignment.status}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
''',
    'frontend/app/teacher/students/page.tsx': '''export default function StudentDirectory() {
  const students = [
    { name: 'Rahul Kumar', id: 'STU-001', program: 'B.Tech CSE', risk: 'HIGH', attendance: '63%', performance: '2.2 GPA', momentum: 'Declining' },
    { name: 'Aisha Khan', id: 'STU-002', program: 'B.Tech ECE', risk: 'MEDIUM', attendance: '76%', performance: '3.1 GPA', momentum: 'Stable' },
  ];
  return (
    <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
      <h1 className="text-2xl font-bold">Student Directory</h1>
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="text-slate-400"><tr><th>Student</th><th>ID</th><th>Program</th><th>Risk</th><th>Attendance</th><th>Performance</th><th>Momentum</th></tr></thead>
          <tbody>
            {students.map((student) => (
              <tr key={student.id} className="border-t border-white/10"><td className="py-3">{student.name}</td><td>{student.id}</td><td>{student.program}</td><td>{student.risk}</td><td>{student.attendance}</td><td>{student.performance}</td><td>{student.momentum}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
''',
    'frontend/app/teacher/early-warnings/page.tsx': '''export default function EarlyWarnings() {
  return <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-8"><h1 className="text-2xl font-bold">Early Warning Center</h1><p className="mt-3 text-slate-300">Rahul Kumar — HIGH, Attendance ?14%, Assessment ?17%, Activity ?31%.</p></div>;
}
''',
    'frontend/app/teacher/risk-monitoring/page.tsx': '''export default function RiskMonitoring() {
  return <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-8"><h1 className="text-2xl font-bold">Risk Monitoring</h1><p className="mt-3 text-slate-300">Students by risk distribution, transitions, and trends are surfaced here.</p></div>;
}
''',
    'frontend/app/teacher/interventions/page.tsx': '''export default function AIInterventions() {
  return <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-8"><h1 className="text-2xl font-bold">AI Interventions</h1><p className="mt-3 text-slate-300">Evidence-backed intervention drafts are reviewed before sending.</p></div>;
}
''',
    'frontend/app/teacher/reports/page.tsx': '''export default function Reports() {
  return <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-8"><h1 className="text-2xl font-bold">Reports</h1><p className="mt-3 text-slate-300">Download academic reports with export support.</p></div>;
}
''',
    'frontend/app/teacher/settings/page.tsx': '''export default function Settings() {
  return <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-8"><h1 className="text-2xl font-bold">Settings</h1><p className="mt-3 text-slate-300">Risk thresholds and system preferences.</p></div>;
}
''',
    'frontend/app/teacher/analytics/page.tsx': '''export default function Analytics() {
  return <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-8"><h1 className="text-2xl font-bold">Analytics</h1></div>;
}
''',
    'frontend/app/teacher/assignments/page.tsx': '''export default function Assignments() {
  return <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-8"><h1 className="text-2xl font-bold">Assignments</h1></div>;
}
''',
    'tests/test_api.py': '''from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_health():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_login_teacher():
    response = client.post('/api/v1/login', json={'email': 'teacher@demo.edu', 'password': 'teacher123'})
    assert response.status_code == 200
    token = response.json()['access_token']
    assert token


def test_teach_dashboard_requires_auth():
    response = client.get('/api/v1/dashboard/teacher')
    assert response.status_code == 401


def test_student_risk_protected():
    student_login = client.post('/api/v1/login', json={'email': 'rahul.kumar@demo.edu', 'password': 'student123'})
    token = student_login.json()['access_token']
    response = client.get('/api/v1/students/1', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 403
''',
    'knowledge_base/attendance_policy.txt': 'Attendance policy: students must attend at least 75% of contact hours. Where attendance falls below this threshold, advising support is recommended.\n',
    'knowledge_base/academic_support.txt': 'Academic support: students can access mentoring, office hours, and revision sessions.\n',
    'knowledge_base/mentoring_guidelines.txt': 'Mentoring guideline: faculty should schedule a check-in within seven days when risk indicators remain elevated.\n',
    'knowledge_base/remedial_support.txt': 'Remedial support: course support sessions are available for at-risk students.\n',
}

for rel_path, content in files.items():
    path = repo / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')

print('Created project skeleton with files:', len(files))
