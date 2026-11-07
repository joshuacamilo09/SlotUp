import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.dependencies import require_admin
from app.models import PasswordResetToken, User
from app.schemas import PasswordResetTokenOut, RoleIn, UserOut
from app.security import hash_reset_token, new_reset_token

log = logging.getLogger("auth.security")
router = APIRouter(prefix="/api/auth/users", tags=["admin"])


def _get_or_404(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilizador não encontrado")
    return user


@router.get("", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at)))


@router.patch("/{user_id}/role", response_model=UserOut)
def change_role(
    user_id: uuid.UUID,
    body: RoleIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    if user_id == admin.id:
        # Evita ficar sem nenhum administrador por engano
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Não pode alterar o seu próprio papel")
    user = _get_or_404(db, user_id)
    user.role = body.role
    db.commit()
    log.info("papel_alterado admin_id=%s user_id=%s novo_papel=%s", admin.id, user.id, body.role)
    return user


@router.post("/{user_id}/2fa/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_2fa(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    """Recuperação de conta: quem perdeu o telemóvel volta a configurar o 2FA no próximo login."""
    user = _get_or_404(db, user_id)
    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            two_fa_enabled=False,
            totp_secret_encrypted=None,
            totp_last_used_step=None,
            failed_login_attempts=0,
            locked_until=None,
        )
    )
    db.commit()
    log.info("2fa_reposto admin_id=%s user_id=%s", admin.id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)



@router.post("/{user_id}/password/reset", response_model=PasswordResetTokenOut, status_code=status.HTTP_201_CREATED)
def create_password_reset(
    user_id: uuid.UUID,
    response: Response,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PasswordResetTokenOut:
    """Recuperação de palavra-passe: gera um token de uso único que o admin entrega ao utilizador.

    * O token aparece só nesta resposta. Na base de dados fica apenas o hash SHA-256.
    * Pedir outra vez anula o token anterior que ainda não foi usado.
    * A palavra-passe antiga continua a funcionar até o token ser usado.
    """
    user = _get_or_404(db, user_id)
    token = new_reset_token()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.password_reset_minutes)

    # Anula o token anterior por usar (o índice password_reset_tokens_one_active só deixa existir um)
    db.execute(
        delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
    )
    db.add(PasswordResetToken(
        user_id=user.id, token_hash=hash_reset_token(token), created_by=admin.id, expires_at=expires_at
    ))
    try:
        db.commit()
    except IntegrityError:
        # Dois admins a pedir ao mesmo tempo (réplicas diferentes): o índice deixa passar só um
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Já foi pedida uma redefinição agora mesmo; tente outra vez") from None

    # Resposta com um segredo: o browser e os proxies não a podem guardar em cache
    response.headers["Cache-Control"] = "no-store"
    log.info("password_reset_pedido admin_id=%s user_id=%s expira=%s", admin.id, user.id, expires_at.isoformat())
    return PasswordResetTokenOut(token=token, expires_at=expires_at)