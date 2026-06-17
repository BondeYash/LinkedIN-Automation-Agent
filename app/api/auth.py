"""Authentication routes — password login that mints a JWT access token."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import get_current_user, get_user_repo
from app.core.security import create_access_token, verify_password
from app.models.models import User
from app.repositories.repos import UserRepository
from app.schemas.auth import Token, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    users: UserRepository = Depends(get_user_repo),
) -> Token:
    """Exchange email (`username`) + password for a bearer JWT."""
    user = users.get_by_email(form.username)
    if user is None or not user.is_active or not verify_password(form.password, user.hashed_pw):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user_id=user.id, role=user.role.value)
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    """Return the authenticated user (verifies the token works)."""
    return user
