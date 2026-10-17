import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.dependencies import current_user, pre_auth_user
from app.models import User
from app.schemas import (
    CodeIn,
    LoginIn,
    PreAuthOut,
    RegisterIn,
    TokenOut,
    TotpSetupOut,
    UserOut,
)
from app.security import (
    burn_password_time,
    create_token,
    decrypt_totp_secret,
    encrypt_totp_secret,
    hash_password,
    match_totp_step,
    new_totp_secret,
    provisioning_uri,
    verify_password,
)

log = logging.getLogger("auth.security")
router = APIRouter(prefix="/api/auth", tags=["auth"])

INVALID_CREDENTIALS = HTTPException(status.HTTP_401_UNAUTHORIZED, "Email ou password inválidos")
INVALID_CODE = HTTPException(status.HTTP_401_UNAUTHORIZED, "Código inválido")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_not_locked(user: User) -> None:
    if user.locked_until and user.locked_until > _now():
        retry = int((user.locked_until - _now()).total_seconds()) + 1
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Demasiadas tentativas falhadas. Tente mais tarde.",
            headers={"Retry-After": str(retry)},
        )


def _register_failure(db: Session, user_id, settings: Settings) -> None:
    """Conta uma tentativa falhada (password ou código) e bloqueia a conta se passar o limite.

    O incremento é feito na própria base de dados (atómico), por isso funciona
    mesmo com várias réplicas do serviço a receber tentativas ao mesmo tempo.
    """
    attempts = db.execute(
        update(User)
        .where(User.id == user_id)
        .values(failed_login_attempts=User.failed_login_attempts + 1)
        .returning(User.failed_login_attempts)
    ).scalar_one()
    if attempts >= settings.max_failed_attempts:
        db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                locked_until=_now() + timedelta(minutes=settings.lock_minutes),
                failed_login_attempts=0,
            )
        )
        log.warning("conta_bloqueada user_id=%s minutos=%s", user_id, settings.lock_minutes)
    db.commit()


def _consume_totp(db: Session, user: User, code: str, settings: Settings) -> None:
    """Valida o código TOTP e marca o passo como usado. Lança 401 se falhar.

    Em caso de sucesso NÃO faz commit: quem chama termina a transação.
    """
    _ensure_not_locked(user)
    secret = decrypt_totp_secret(settings, user.totp_secret_encrypted, user.id)
    step = match_totp_step(secret, code)
    accepted = False
    if step is not None:
        # Só aceita se o passo for mais recente que o último usado. O UPDATE
        # condicional é atómico: duas réplicas não aceitam o mesmo código duas vezes.
        result = db.execute(
            update(User)
            .where(
                User.id == user.id,
                or_(User.totp_last_used_step.is_(None), User.totp_last_used_step < step),
            )
            .values(totp_last_used_step=step)
        )
        accepted = result.rowcount == 1
    if not accepted:
        _register_failure(db, user.id, settings)
        raise INVALID_CODE


def _issue_access_token(db: Session, user: User, settings: Settings) -> TokenOut:
    db.execute(
        update(User).where(User.id == user.id).values(failed_login_attempts=0, locked_until=None)
    )
    db.commit()
    token = create_token(
        settings,
        subject=user.id,
        typ="access",
        minutes=settings.access_token_minutes,
        claims={"email": user.email, "role": user.role},
    )
    return TokenOut(access_token=token, expires_in=settings.access_token_minutes * 60)


# --------------------------------------------------------------------------- registo e login
@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> User:
    user = User(
        name=body.name.strip(),
        email=body.email.lower(),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Este email já está registado") from None
    return user


@router.post("/login", response_model=PreAuthOut)
def login(
    body: LoginIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PreAuthOut:
    """Passo 1: email + password. Devolve um token temporário para o passo 2 (2FA)."""
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    if user is None:
        burn_password_time(body.password)
        raise INVALID_CREDENTIALS
    _ensure_not_locked(user)
    if not user.is_active or not verify_password(user.password_hash, body.password):
        _register_failure(db, user.id, settings)
        raise INVALID_CREDENTIALS

    stage = "verify" if user.two_fa_enabled else "setup"
    token = create_token(
        settings,
        subject=user.id,
        typ="pre_auth",
        minutes=settings.pre_auth_token_minutes,
        claims={"stage": stage},
    )
    return PreAuthOut(
        status="MFA_REQUIRED" if user.two_fa_enabled else "MFA_SETUP_REQUIRED",
        pre_auth_token=token,
        expires_in=settings.pre_auth_token_minutes * 60,
    )


# --------------------------------------------------------------------------- 2FA
@router.post("/2fa/setup", response_model=TotpSetupOut)
def setup_2fa(
    user: User = Depends(pre_auth_user("setup")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TotpSetupOut:
    """Gera o segredo TOTP. O frontend mostra o QR code a partir do otpauth_uri."""
    if user.two_fa_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "O 2FA já está ativo")
    if user.totp_secret_encrypted:
        # Já existe um segredo ainda não confirmado: reutiliza (ex.: o utilizador recarregou a página)
        secret = decrypt_totp_secret(settings, user.totp_secret_encrypted, user.id)
    else:
        secret = new_totp_secret()
        user.totp_secret_encrypted = encrypt_totp_secret(settings, secret, user.id)
        db.commit()
    return TotpSetupOut(secret=secret, otpauth_uri=provisioning_uri(secret, user.email, settings.totp_issuer))


@router.post("/2fa/enable", response_model=TokenOut)
def enable_2fa(
    body: CodeIn,
    user: User = Depends(pre_auth_user("setup")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenOut:
    """Confirma o primeiro código, ativa o 2FA e conclui o login."""
    if user.two_fa_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "O 2FA já está ativo")
    if not user.totp_secret_encrypted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chame primeiro /2fa/setup")
    _consume_totp(db, user, body.code, settings)
    db.execute(update(User).where(User.id == user.id).values(two_fa_enabled=True))
    log.info("2fa_ativado user_id=%s", user.id)
    return _issue_access_token(db, user, settings)


@router.post("/2fa/verify", response_model=TokenOut)
def verify_2fa(
    body: CodeIn,
    user: User = Depends(pre_auth_user("verify")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenOut:
    """Passo 2 do login: valida o código da app Authenticator e devolve o token de acesso."""
    if not user.two_fa_enabled or not user.totp_secret_encrypted:
        raise HTTPException(status.HTTP_409_CONFLICT, "O 2FA não está ativo")
    _consume_totp(db, user, body.code, settings)
    return _issue_access_token(db, user, settings)


# --------------------------------------------------------------------------- perfil
@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user
