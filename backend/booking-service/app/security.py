"""Validação dos tokens emitidos pelo auth-service.

Este serviço NÃO chama o auth a cada pedido: verifica a assinatura RS256 com a
chave pública e confia nas informações (id, email, papel) que vêm dentro do token.
Consequência: se um administrador mudar o papel de alguém, o token antigo continua
válido até expirar (30 min por omissão).
"""
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    email: str
    role: str


@lru_cache
def _public_key(path: str) -> str:
    return Path(path).read_text()


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Token em falta ou inválido", headers={"WWW-Authenticate": "Bearer"}
    )


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if creds is None:
        raise _unauthorized()
    try:
        payload = jwt.decode(
            creds.credentials,
            _public_key(settings.jwt_public_key_file),
            algorithms=["RS256"],  # fixo: impede ataques com "alg": "none" ou HS256
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "typ"]},
        )
        if payload["typ"] != "access":  # tokens "pre_auth" (2FA incompleto) não servem aqui
            raise _unauthorized()
        return CurrentUser(id=uuid.UUID(payload["sub"]), email=payload["email"], role=payload["role"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise _unauthorized() from None


def require_admin(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if user.role != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas administradores")
    return user
