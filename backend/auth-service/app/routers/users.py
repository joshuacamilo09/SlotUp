import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models import User
from app.schemas import RoleIn, UserOut

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
