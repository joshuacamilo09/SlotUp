"""Criar reservas.

POST /api/reservas/reservas   {resource_id, start_at, end_at}

* Qualquer usuário autenticado (inclusive o ADMIN) reserva em nome próprio: o id e o
  email vêm do token (JWT), nunca do corpo do pedido.
* A reserva tem de caber inteira num intervalo de abertura do recurso, não pode começar
  no passado nem a mais de 30 dias, e usa horas múltiplas de 15 min (mínimo 15 min).
* Horas sem fuso valem como hora local do complexo (LOCAL_TIMEZONE).
* Quem garante que dois pedidos não ficam com o mesmo horário é o PostgreSQL
  (constraint reservations_no_overlap), e não um SELECT antes do INSERT. Com várias
  réplicas, dois pedidos simultâneos podiam passar os dois no SELECT; no banco, só
  o primeiro INSERT passa, e o segundo recebe 409.
* Na mesma transação grava o pedido de email (tabela notifications, padrão outbox).
"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import Notification, Reservation, Resource
from app.schemas import ReservationCreate, ReservationOut
from app.security import CurrentUser, current_user

log = logging.getLogger("booking.reservations")
router = APIRouter(prefix="/api/reservas/reservas", tags=["reservas"])

SLOT_MINUTES = 15
MAX_DAYS_AHEAD = 30
_NO_OVERLAP = "reservations_no_overlap"

def _unprocessable(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)

def _to_local(value: datetime, tz: ZoneInfo) -> datetime:
    """Sem fuso: é hora local, só acrescentamos o fuso. Com fuso: convertemos para a hora local."""
    return value.replace(tzinfo=tz) if value.tzinfo is None else value.astimezone(tz)

def _on_grid(value: datetime) -> bool:
    """True se a hora for exata num múltiplo de 15 min (sem segundos)."""
    return value.minute % SLOT_MINUTES == 0 and value.second == 0 and value.microsecond == 0

def _fits_opening(resource: Resource, start: datetime, end: datetime) -> bool:
    """True se [start, end] couber inteiro num dos intervalos de abertura desse dia."""
    if start.date() != end.date():
        return False
    return any(
        rule.weekday == start.weekday() and rule.open_time <= start.time() and end.time() <= rule.close_time
        for rule in resource.rules
    )

def _constraint_name(exc: IntegrityError) -> str | None:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)

@router.post("", response_model=ReservationOut, status_code=status.HTTP_201_CREATED)
def create_reservation(
    body: ReservationCreate,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Reservation:
    tz = ZoneInfo(settings.local_timezone)
    start, end = _to_local(body.start_at, tz), _to_local(body.end_at, tz)

    # 1) Regras de horário que não dependem do recurso
    if not (_on_grid(start) and _on_grid(end)):
        raise _unprocessable(f"Use horas múltiplas de {SLOT_MINUTES} minutos (ex.: 09:00, 09:15)")
    now = datetime.now(tz)
    if start < now:
        raise _unprocessable("Não é possível reservar no passado")
    if start > now + timedelta(days=MAX_DAYS_AHEAD):
        raise _unprocessable(f"Só é possível reservar com até {MAX_DAYS_AHEAD} dias de antecedência")

    # 2) O recurso tem de existir e estar ativo (mesmo para o ADMIN: não se reserva um recurso desativado)
    resource = db.get(Resource, body.resource_id)
    if resource is None or not (resource.is_active and resource.category.is_active):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurso não encontrado")
    if not _fits_opening(resource, start, end):
        raise _unprocessable("O horário está fora do horário de funcionamento do recurso")

    # 3) Grava a reserva. O flush() envia o INSERT já, e é nesse momento que o banco
    #    confere a constraint contra sobreposição (atômica, vale para todas as réplicas).
    reservation = Reservation(
        user_id=user.id,
        user_email=user.email,
        resource_id=resource.id,
        start_at=start,
        end_at=end,
        status="CONFIRMED",
    )
    db.add(reservation)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if _constraint_name(exc) == _NO_OVERLAP:
            raise HTTPException(status.HTTP_409_CONFLICT, "Este horário já está resrevado") from None
        raise

    # 4) Pedido de email na mesma transação (outbox): ou ficam os dois, ou nenhum
    db.add(
        Notification(
            user_id=user.id,
            recipient_email=user.email,
            type="RESERVATION_CREATED",
            reservation_id=reservation.id,
            payload={"resource_name": resource.name, "start_at": start.isoformat(), "end_at": end.isoformat()},
        )
    )
    db.commit()
    db.refresh(reservation)

    log.info("reserva_criada user_id=%s reserva_id=%s recurso_id=%s", user.id, reservation.id, resource.id)
    return reservation