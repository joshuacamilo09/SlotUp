"""Testes de integração: correm contra o PostgreSQL real do Docker Compose.

Antes de correr:   cd infra/docker && docker compose up -d db
Variáveis úteis:   AUTH_DB_PASSWORD (a do seu .env), DB_HOST (localhost), DB_PORT (5436)
"""
import base64
import os
import tempfile
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# --- configuração de teste: tem de ser definida ANTES de importar a aplicação
_tmp = Path(tempfile.mkdtemp(prefix="slotup-auth-tests-"))
_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
(_tmp / "private.pem").write_bytes(
    _key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
)
(_tmp / "public.pem").write_bytes(
    _key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
)
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5436")
os.environ.setdefault("DB_PASSWORD", os.environ.get("AUTH_DB_PASSWORD", "troque-me"))
os.environ["JWT_PRIVATE_KEY_FILE"] = str(_tmp / "private.pem")
os.environ["JWT_PUBLIC_KEY_FILE"] = str(_tmp / "public.pem")
os.environ["TOTP_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
os.environ["MAX_FAILED_ATTEMPTS"] = "3"
os.environ.pop("ADMIN_EMAIL", None)
os.environ.pop("ADMIN_PASSWORD", None)

import pyotp  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text, update  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.security import decrypt_totp_secret  # noqa: E402

PASSWORD = "uma-password-segura-123"


@pytest.fixture(scope="session", autouse=True)
def _database_is_up():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.exit(
            "Base de dados inacessível. Suba-a com 'docker compose up -d db' em infra/docker "
            f"e defina AUTH_DB_PASSWORD. Erro: {exc.__class__.__name__}",
            returncode=2,
        )


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def new_email() -> str:
    return f"teste-{uuid.uuid4().hex[:12]}@slotup.pt"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def totp_code(secret: str, offset_seconds: int = 0) -> str:
    import time

    return pyotp.TOTP(secret).at(int(time.time()) + offset_seconds)


def get_user(email: str) -> User:
    with SessionLocal() as db:
        return db.query(User).filter(User.email == email).one()


def stored_secret(email: str) -> str:
    user = get_user(email)
    return decrypt_totp_secret(get_settings(), user.totp_secret_encrypted, user.id)


def set_role(email: str, role: str) -> None:
    with SessionLocal() as db:
        db.execute(update(User).where(User.email == email).values(role=role))
        db.commit()


@pytest.fixture
def registered(client):
    """Um utilizador novo, ainda sem 2FA."""
    email = new_email()
    r = client.post("/api/auth/register", json={"name": "Teste", "email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return email


def full_login(client, email: str, secret: str | None = None, offset: int = 0) -> tuple[str, str]:
    """Faz o login completo (com setup do 2FA na primeira vez). Devolve (access_token, segredo)."""
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    body = r.json()
    if body["status"] == "MFA_SETUP_REQUIRED":
        token = body["pre_auth_token"]
        setup = client.post("/api/auth/2fa/setup", headers=bearer(token)).json()
        secret = setup["secret"]
        r = client.post("/api/auth/2fa/enable", json={"code": totp_code(secret, offset)}, headers=bearer(token))
    else:
        r = client.post(
            "/api/auth/2fa/verify",
            json={"code": totp_code(secret, offset)},
            headers=bearer(body["pre_auth_token"]),
        )
    assert r.status_code == 200, r.text
    return r.json()["access_token"], secret


@pytest.fixture
def user_with_2fa(client, registered):
    token, secret = full_login(client, registered)
    return {"email": registered, "token": token, "secret": secret}
