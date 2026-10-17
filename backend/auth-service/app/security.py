"""Tudo o que é criptografia: passwords, JWT e TOTP."""
import base64
import hmac
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import Settings

# --------------------------------------------------------------------------- passwords
_hasher = PasswordHasher()  # Argon2id com parâmetros por omissão recomendados
_DUMMY_HASH = _hasher.hash("password-falsa-para-igualar-o-tempo")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def burn_password_time(password: str) -> None:
    """Gasta o mesmo tempo que uma verificação real.

    Chamado quando o email não existe, para que o tempo de resposta não revele
    quais emails estão registados.
    """
    verify_password(_DUMMY_HASH, password)


# --------------------------------------------------------------------------- JWT (RS256)
@lru_cache
def _read_key(path: str) -> str:
    return Path(path).read_text()


def create_token(
    settings: Settings,
    *,
    subject: uuid.UUID,
    typ: str,
    minutes: int,
    claims: dict | None = None,
) -> str:
    """typ = "access" (acesso total) ou "pre_auth" (só serve para completar o 2FA)."""
    now = datetime.now(timezone.utc)
    payload = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": str(subject),
        "typ": typ,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        "jti": uuid.uuid4().hex,
        **(claims or {}),
    }
    return jwt.encode(payload, _read_key(settings.jwt_private_key_file), algorithm="RS256")


def decode_token(settings: Settings, token: str) -> dict:
    """Valida assinatura, emissor, audiência e expiração. Lança jwt.PyJWTError se falhar."""
    return jwt.decode(
        token,
        _read_key(settings.jwt_public_key_file),
        algorithms=["RS256"],  # fixo: nunca aceitar o algoritmo que vem no token
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
        options={"require": ["exp", "iat", "sub", "typ"]},
    )


# --------------------------------------------------------------------------- TOTP
TOTP_PERIOD = 30


def new_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str, issuer: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def match_totp_step(secret: str, code: str, now: float | None = None) -> int | None:
    """Devolve o time-step a que o código corresponde, ou None.

    Aceita o passo atual e os dois vizinhos (±30 s) para tolerar relógios
    ligeiramente desfasados. O passo devolvido serve para impedir reutilização.
    """
    totp = pyotp.TOTP(secret)  # 6 dígitos, 30 s, SHA-1: compatível com Google/Microsoft Authenticator
    current = int((time.time() if now is None else now) // TOTP_PERIOD)
    for step in (current, current - 1, current + 1):
        if hmac.compare_digest(totp.at(step * TOTP_PERIOD), code):
            return step
    return None


# --------------------------------------------------------------------------- cifra do segredo TOTP
def _aesgcm(settings: Settings) -> AESGCM:
    key = base64.urlsafe_b64decode(settings.totp_key_b64())
    if len(key) != 32:
        raise ValueError("TOTP_ENCRYPTION_KEY tem de ter exatamente 32 bytes (em base64)")
    return AESGCM(key)


def encrypt_totp_secret(settings: Settings, secret: str, user_id: uuid.UUID) -> bytes:
    nonce = os.urandom(12)
    # O id do utilizador entra como "dados associados": o segredo cifrado de um
    # utilizador não pode ser copiado para a linha de outro.
    return nonce + _aesgcm(settings).encrypt(nonce, secret.encode(), user_id.bytes)


def decrypt_totp_secret(settings: Settings, blob: bytes, user_id: uuid.UUID) -> str:
    nonce, ciphertext = blob[:12], blob[12:]
    return _aesgcm(settings).decrypt(nonce, ciphertext, user_id.bytes).decode()
