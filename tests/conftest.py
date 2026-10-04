import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models import AssignmentStudent, Student, User
from backend.app.services.auth import hash_password


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    with TestingSession() as db:
        teacher = User(email='teacher@example.com', full_name='Test Teacher', role='TEACHER', password_hash=hash_password('teacher-pass'))
        student_user = User(email='student@example.com', full_name='Student One', role='STUDENT', password_hash=hash_password('student-pass'))
        other_user = User(email='other@example.com', full_name='Student Two', role='STUDENT', password_hash=hash_password('other-pass'))
        db.add_all([teacher, student_user, other_user])
        db.flush()
        student = Student(student_id='T-001', full_name='Student One', section='A', risk_level='HIGH', risk_probability=0.8)
        other = Student(student_id='T-002', full_name='Student Two', section='B', risk_level='LOW', risk_probability=0.1)
        db.add_all([student, other])
        db.flush()
        student.user_id = student_user.id
        other.user_id = other_user.id
        db.commit()
        app.state.test_student_id = student.id
        app.state.test_other_student_id = other.id
        app.state.test_session_factory = TestingSession

    def override_get_db():
        with TestingSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr('backend.app.main.settings.upload_directory', tmp_path / 'uploads')
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    del app.state.test_session_factory
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def teacher_token(client):
    response = client.post('/api/v1/auth/login', json={'email': 'teacher@example.com', 'password': 'teacher-pass'})
    assert response.status_code == 200
    return response.json()['access_token']


@pytest.fixture
def student_token(client):
    response = client.post('/api/v1/auth/login', json={'email': 'student@example.com', 'password': 'student-pass'})
    assert response.status_code == 200
    return response.json()['access_token']