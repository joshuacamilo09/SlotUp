import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import User
from app.security import decode_token

_bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Token em falta ou inválido") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def _load_user(
    creds: HTTPAuthorizationCredentials | None,
    expected_typ: str,
    db: Session,
    settings: Settings,
    expected_stage: str | None = None,
) -> User:
    if creds is None:
        raise _unauthorized()
    try:
        payload = decode_token(settings, creds.credentials)
    except jwt.PyJWTError:
        raise _unauthorized() from None
    # Um token "pre_auth" nunca serve como "access" e vice-versa.
    if payload.get("typ") != expected_typ:
        raise _unauthorized()
    if expected_stage is not None and payload.get("stage") != expected_stage:
        raise _unauthorized()
    try:
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (ValueError, KeyError):
        raise _unauthorized() from None
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    return _load_user(creds, "access", db, settings)


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas administradores")
    return user


def pre_auth_user(stage: str):
    """Dependência para os endpoints do 2FA: exige um token pre_auth do estágio certo."""

    def dependency(
        creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
        db: Session = Depends(get_db),
        settings: Settings = Depends(get_settings),
    ) -> User:
        return _load_user(creds, "pre_auth", db, settings, expected_stage=stage)

    return dependency
