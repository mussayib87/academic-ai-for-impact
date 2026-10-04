from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from backend.app.core.security import CurrentUser
from backend.app.database import get_db
from backend.app.models import User
from backend.app.services.auth import create_access_token, verify_password

router = APIRouter(prefix='/auth', tags=['authentication'])
DatabaseSession = Annotated[Session, Depends(get_db)]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    user: dict[str, str | int | None]


@router.post('/login', response_model=LoginResponse)
def login(payload: LoginRequest, db: DatabaseSession) -> LoginResponse:
    email = str(payload.email).lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid email or password')
    return LoginResponse(
        access_token=create_access_token(user.email, user.role),
        user={'id': user.id, 'email': user.email, 'name': user.full_name, 'role': user.role.upper()},
    )


@router.get('/me')
def me(user: CurrentUser) -> dict[str, str | int | None]:
    return {'id': user.id, 'email': user.email, 'name': user.full_name, 'role': user.role.upper()}