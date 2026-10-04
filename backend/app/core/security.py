from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Student, Teacher, User
from backend.app.services.auth import decode_token

bearer_scheme = HTTPBearer(auto_error=False)
DatabaseSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DatabaseSession,
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Authentication required',
        headers={'WWW-Authenticate': 'Bearer'},
    )
    if credentials is None:
        raise unauthorized
    try:
        claims: dict[str, Any] = decode_token(credentials.credentials)
        email = claims.get('sub')
        if not isinstance(email, str):
            raise unauthorized
    except (jwt.PyJWTError, ValueError):
        raise unauthorized from None
    user = db.query(User).filter(User.email == email.lower()).first()
    if user is None:
        raise unauthorized
    return user


def get_current_teacher(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role.upper() != 'TEACHER':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Teacher access required')
    return user


def get_current_student(
    user: Annotated[User, Depends(get_current_user)],
    db: DatabaseSession,
) -> Student:
    if user.role.upper() != 'STUDENT' or user.student is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Student access required')
    student = db.query(Student).filter(Student.user_id == user.id).first()
    if student is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Student profile is not linked')
    return student


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentTeacher = Annotated[User, Depends(get_current_teacher)]
CurrentStudent = Annotated[Student, Depends(get_current_student)]