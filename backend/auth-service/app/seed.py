"""Dados de exemplo do auth-service (SÓ para desenvolvimento e demo).

Cria ou atualiza dois usuários, sempre no mesmo estado:
  * o administrador do .env (ADMIN_EMAIL / ADMIN_PASSWORD);
  * a usuária comum ana@slotup.pt (senha SEED_USER_PASSWORD).

Os dois ficam com o 2FA JÁ ATIVO, com o mesmo segredo TOTP fixo (SEED_TOTP_SECRET).
Assim basta adicionar a conta no Authenticator uma vez: continua a valer depois de
um `docker compose down -v`.

Rodar:  docker compose exec auth python -m app.seed
"""
import os
import sys
import uuid

import pyotp
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import User
from app.security import encrypt_totp_secret, hash_password, provisioning_uri

# Usuária de exemplo
DEMO_USER_NAME = "Ana Silva"
DEMO_USER_EMAIL = "ana@slotup.pt"

def _requirede_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Defina {nome} no infra/docker/.env")
    return value

def _check_totp_secret(secret: str) -> None:
    try:
        pyotp.TOTP(secret).now()
    except Exception:
        sys.exit("SEED_TOTP_SECRET inválido. Gere um com: python -c \"import pyotp; print(pyotp.random_base32())\"")

def _upsert_user(db, settings, *, name: str, email: str, password: str, role: str, totp_secret: str) -> None:
    email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(id=uuid.uuid4(), email=email)
        db.add(user)
        
    user.name = name
    user.password_hash = hash_password(password)
    user.role = role
    user.is_active = True
    user.two_fa_enabled = True
    user.totp_secret_encrypted = encrypt_totp_secret(settings, totp_secret, user.id)
    user.totp_last_used_step = None
    user.failed_login_attempts = 0
    user.locked_until = None

def main() -> None:
    if os.environ.get("SEED_ENABLED", "").lower() != "true":
        sys.exit("SEED_ENABLED não está ativo: o seed só roda em desenvolvimento.")

    settings = get_settings()
    if not(settings.admin_email and settings.admin_password):
        sys.exit("Defina ADMIN_EMAIL e ADMIN_PASSWORD no infra/docker/.env")

    totp_secret = _requirede_env("SEED_TOTP_SECRET")
    _check_totp_secret(totp_secret)
    user_password = _requirede_env("SEED_USER_PASSWORD")

    with SessionLocal() as db:
        _upsert_user(db, settings, name=settings.admin_name or "Administrador", email=settings.admin_email,
                     password=settings.admin_password, role="ADMIN", totp_secret=totp_secret)
        _upsert_user(db, settings, name=DEMO_USER_NAME, email=DEMO_USER_EMAIL,
                     password=user_password, role="USER", totp_secret=totp_secret)
        db.commit()

    print(f"OK: {settings.admin_email.lower()} (ADMIN) e {DEMO_USER_EMAIL} (USER) prontos, com 2FA ativo.")
    print("Authenticator:", provisioning_uri(totp_secret, "demo@slotup", settings.totp_issuer))

if __name__ == "__main__":
    main()