"""Auth: register, login, and who-am-I."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import AuditEvent, Role, User
from ..schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from ..security import PasswordTooLongError, create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists.",
        )

    try:
        password_hash = hash_password(payload.password)
    except PasswordTooLongError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    # Self-registration is always the lowest privileged role. Admin is granted
    # out of band (see docs/setup.md) — never by a request body.
    user = User(email=payload.email.lower(), password_hash=password_hash, role=Role.viewer)
    db.add(user)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="user.registered",
            entity_type="user",
            entity_id=user.id,
            detail={"email": user.email},
        )
    )
    db.commit()

    return TokenResponse(access_token=create_access_token(user.id, user.role.value), role=user.role)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    # Same message and same work for "no such user" and "wrong password" so the
    # endpoint cannot be used to enumerate accounts.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    return TokenResponse(access_token=create_access_token(user.id, user.role.value), role=user.role)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
