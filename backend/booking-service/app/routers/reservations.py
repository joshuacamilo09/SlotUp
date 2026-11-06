"""Criar, consultar e cancelar reservas.

POST /api/reservas/reservas   {resource_id, start_at, end_at}
(as rotas de consultar e cancelar estão no fim do ficheiro)

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
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import Notification, Reservation, Resource
from app.schemas import Periodo, ReservationAdminOut, ReservationCreate, ReservationOut, ReservationStatus
from app.security import CurrentUser, current_user, require_admin

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

def check_slot(db: Session, body: ReservationCreate, settings: Settings) -> tuple[Resource, datetime, datetime]:
    """Regras de horário de uma reserva (também usadas ao entrar na fila de espera).

    Devolve o recurso e o início e fim em hora local. Erro: 422 (regra) ou 404 (recurso).
    """
    tz = ZoneInfo(settings.local_timezone)

    if not _fits_opening(resource, start, end):
        raise _unprocessable("O horário está fora do horário de funcionamento do recurso")

    return resource, start, end


@router.post("", response_model=ReservationOut, status_code=status.HTTP_201_CREATED)
def create_reservation(
    body: ReservationCreate,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Reservation:
    # 1) e 2) Regras de horário e do recurso
    resource, start, end = check_slot(db, body, settings)

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
            raise HTTPException(status.HTTP_409_CONFLICT, "Este horário já está reservado") from None
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



# =========================================================================== consultar e cancelar
# GET  /api/reservas/reservas/minhas            as reservas de quem pede (futuras e passadas)
# GET  /api/reservas/reservas                   todas as reservas (só ADMIN), com filtros
# GET  /api/reservas/reservas/{id}              uma reserva (o dono ou o ADMIN)
# POST /api/reservas/reservas/{id}/cancelar     cancela (o dono, antes de começar; o ADMIN, até acabar)

# Estados que ainda ocupam o horário (os mesmos da constraint reservations_no_overlap)
ACTIVE_STATUSES = ("HELD", "CONFIRMED")


def _filtered(
    query: Select, response: Response, db: Session, periodo: Periodo, limit: int, offset: int
) -> list[Reservation]:
    """Aplica o período, a ordem e a paginação. O total vai no cabeçalho X-Total-Count.

    Futura = ainda não acabou (uma reserva a decorrer conta como futura).
    Futuras: a mais próxima primeiro. Passadas e todas: a mais recente primeiro.
    O id no fim da ordem deixa a paginação estável quando há horas iguais.
    """
    now = datetime.now(timezone.utc)
    if periodo == "futuras":
        query = query.where(Reservation.end_at > now).order_by(Reservation.start_at, Reservation.id)
    elif periodo == "passadas":
        query = query.where(Reservation.end_at <= now).order_by(Reservation.start_at.desc(), Reservation.id)
    else:
        query = query.order_by(Reservation.start_at.desc(), Reservation.id)

    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    response.headers["X-Total-Count"] = str(total)
    return list(db.scalars(query.limit(limit).offset(offset)))


@router.get("/minhas", response_model=list[ReservationOut])
def list_my_reservations(
    response: Response,
    periodo: Periodo = Query("todas", description="futuras, passadas ou todas"),
    status_filter: ReservationStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[Reservation]:
    # Só as do próprio: o filtro usa o id do token, nunca um parâmetro do pedido
    query = select(Reservation).where(Reservation.user_id == user.id)
    if status_filter:
        query = query.where(Reservation.status == status_filter)
    return _filtered(query, response, db, periodo, limit, offset)



@router.get("", response_model=list[ReservationAdminOut])
def list_all_reservations(
    response: Response,
    periodo: Periodo = Query("todas", description="futuras, passadas ou todas"),
    status_filter: ReservationStatus | None = Query(None, alias="status"),
    resource_id: uuid.UUID | None = Query(None),
    user_email: str | None = Query(None, max_length=255, description="Email exato (não diferencia maiúsculas)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Reservation]:
    query = select(Reservation)
    if status_filter:
        query = query.where(Reservation.status == status_filter)
    if resource_id:
        query = query.where(Reservation.resource_id == resource_id)
    if user_email:
        query = query.where(func.lower(Reservation.user_email) == user_email.strip().lower())
    return _filtered(query, response, db, periodo, limit, offset)



def _get_visible(db: Session, reservation_id: uuid.UUID, user: CurrentUser, *, lock: bool = False) -> Reservation:
    """A reserva, se quem pede for o dono ou o ADMIN. A de outra pessoa dá 404, e não 403:
    assim ninguém consegue descobrir que ids de reservas existem (ataque IDOR).

    lock=True bloqueia a linha até ao commit (SELECT ... FOR UPDATE).
    """
    query = select(Reservation).where(Reservation.id == reservation_id)
    if lock:
        query = query.with_for_update(of=Reservation)
    reservation = db.scalars(query).first()
    if reservation is None or (reservation.user_id != user.id and user.role != "ADMIN"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reserva não encontrada")
    return reservation


@router.get("/{reservation_id}", response_model=ReservationOut)
def get_reservation(
    reservation_id: uuid.UUID,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> Reservation:
    return _get_visible(db, reservation_id, user)


@router.post("/{reservation_id}/cancelar", response_model=ReservationOut)
def cancel_reservation(
    reservation_id: uuid.UUID,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> Reservation:
    """Cancela a reserva e o horário volta a ficar livre.

    * O dono cancela a sua, só antes de ela começar. O ADMIN cancela qualquer uma, até ela acabar.
    * Reserva já cancelada, ou já terminada, dá 409.
    * A linha fica bloqueada (FOR UPDATE) até ao commit: se o dono e o admin cancelarem ao
      mesmo tempo, o segundo espera, vê a reserva já CANCELLED e recebe 409. Só sai um email.
    * O horário fica livre sozinho: a constraint reservations_no_overlap só olha para
      HELD e CONFIRMED, por isso uma reserva CANCELLED deixa de contar.
    """
    reservation = _get_visible(db, reservation_id, user, lock=True)
    now = datetime.now(timezone.utc)
    is_admin = user.role == "ADMIN"

    if reservation.status not in ACTIVE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "A reserva já está cancelada")
    if reservation.end_at <= now:
        raise HTTPException(status.HTTP_409_CONFLICT, "A reserva já terminou")
    if reservation.start_at <= now and not is_admin:
        raise HTTPException(status.HTTP_409_CONFLICT, "A reserva já começou e não pode ser cancelada")

    reservation.status = "CANCELLED"
    reservation.cancelled_at = now  # obrigatório: CHECK reservations_cancelled_has_date (migração 0002)
    reservation.version += 1

    # Email para o DONO da reserva (mesmo quando quem cancela é o admin), na mesma transação (outbox)
    db.add(
        Notification(
            user_id=reservation.user_id,
            recipient_email=reservation.user_email,
            type="RESERVATION_CANCELLED",
            reservation_id=reservation.id,
            payload={
                "resource_name": reservation.resource_name,
                "start_at": reservation.start_at.isoformat(),
                "end_at": reservation.end_at.isoformat(),
                "cancelled_by": "ADMIN" if is_admin and reservation.user_id != user.id else "USER",
            },
        )
    )
    db.commit()
    db.refresh(reservation)

    log.info("reserva_cancelada por_user_id=%s papel=%s reserva_id=%s", user.id, user.role, reservation.id)
    return reservation
