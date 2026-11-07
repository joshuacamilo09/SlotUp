"""Fila de espera.

POST /api/reservas/fila                     {resource_id, start_at, end_at}  entrar na fila de um horário ocupado
GET  /api/reservas/fila/minhas              os meus pedidos, com a posição na fila e a oferta (se houver)
POST /api/reservas/fila/{id}/aceitar        aceita a oferta: a reserva HELD passa a CONFIRMED
POST /api/reservas/fila/{id}/sair           sai da fila; se já tinha oferta, recusa-a e o horário passa ao seguinte

As regras partilhadas (oferecer, libertar, expirar) estão em app/waitlist.py.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import waitlist
from app.config import Settings, get_settings
from app.database import get_db
from app.models import Notification, Reservation, WaitlistEntry
from app.routers.reservations import ACTIVE_STATUSES, check_slot
from app.schemas import ReservationCreate, ReservationOut, WaitlistOut
from app.security import CurrentUser, current_user

log = logging.getLogger("booking.waitlist")
router = APIRouter(prefix="/api/reservas/fila", tags=["fila de espera"])

_ONE_PER_SLOT = "waitlist_one_active_per_slot"


def _out(db: Session, entry: WaitlistEntry) -> WaitlistOut:
    out = WaitlistOut.model_validate(entry)
    out.position = waitlist.queue_position(db, entry)
    return out


def _lock(db: Session, entry: WaitlistEntry) -> None:
    """Bloqueia a linha do pedido até ao commit e relê-a (outra transação pode tê-la mudado)."""
    db.scalars(
        select(WaitlistEntry)
        .where(WaitlistEntry.id == entry.id)
        .with_for_update(of=WaitlistEntry)
        .execution_options(populate_existing=True)
    ).one()


def _get_own(db: Session, entry_id: uuid.UUID, user: CurrentUser) -> WaitlistEntry:
    """O pedido, se for de quem pede. O de outra pessoa dá 404 (não se revela que existe)."""
    entry = db.get(WaitlistEntry, entry_id)
    if entry is None or entry.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pedido não encontrado")
    return entry


@router.post("", response_model=WaitlistOut, status_code=status.HTTP_201_CREATED)
def join_waitlist(
    body: ReservationCreate,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WaitlistOut:
    # Mesmas regras de uma reserva: horas de 15 em 15 min, futuro, até 30 dias, dentro do horário de abertura
    resource, start, end = check_slot(db, body, settings)

    blocking = db.scalars(
        select(Reservation).where(
            Reservation.resource_id == resource.id,
            Reservation.status.in_(ACTIVE_STATUSES),
            Reservation.start_at < end,
            Reservation.end_at > start,
        )
    ).all()
    if not blocking:
        raise HTTPException(status.HTTP_409_CONFLICT, "O horário está livre: faça a reserva diretamente")
    if any(r.user_id == user.id for r in blocking):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já tem uma reserva neste horário")

    entry = WaitlistEntry(
        user_id=user.id, user_email=user.email, resource_id=resource.id, desired_start=start, desired_end=end
    )
    db.add(entry)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == _ONE_PER_SLOT:
            raise HTTPException(status.HTTP_409_CONFLICT, "Já está na fila para este horário") from None
        raise

    db.add(
        Notification(
            user_id=user.id,
            recipient_email=user.email,
            type="WAITLIST_JOINED",
            waitlist_entry_id=entry.id,
            payload={"resource_name": resource.name, "start_at": start.isoformat(), "end_at": end.isoformat()},
        )
    )
    # Se, entretanto, alguém cancelou (corrida com o SELECT de cima), a oferta sai já
    waitlist.offer_freed_slot(db, resource.id, start, end, datetime.now(timezone.utc))
    db.commit()
    db.refresh(entry)

    log.info("fila_entrada user_id=%s entrada_id=%s recurso_id=%s", user.id, entry.id, resource.id)
    return _out(db, entry)


@router.get("/minhas", response_model=list[WaitlistOut])
def list_my_entries(user: CurrentUser = Depends(current_user), db: Session = Depends(get_db)) -> list[WaitlistOut]:
    entries = db.scalars(
        select(WaitlistEntry)
        .where(WaitlistEntry.user_id == user.id)
        .order_by(WaitlistEntry.desired_start.desc(), WaitlistEntry.id)
        .limit(200)
    ).all()
    return [_out(db, e) for e in entries]


@router.post("/{entry_id}/aceitar", response_model=ReservationOut)
def accept_offer(
    entry_id: uuid.UUID,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> Reservation:
    """Aceita a oferta: a reserva HELD passa a CONFIRMED. Oferta fora de prazo: 409, e passa ao seguinte."""
    entry = _get_own(db, entry_id, user)
    if entry.status != "OFFERED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Este pedido não tem nenhuma oferta para aceitar")

    # Bloqueia primeiro a reserva e depois o pedido: a mesma ordem de cancelar e de expirar,
    # para duas transações nunca ficarem à espera uma da outra (deadlock)
    hold = db.scalars(
        select(Reservation).where(Reservation.id == entry.reservation_id).with_for_update(of=Reservation)
    ).one()
    _lock(db, entry)
    now = datetime.now(timezone.utc)

    if entry.status != "OFFERED" or hold.status != "HELD":
        raise HTTPException(status.HTTP_409_CONFLICT, "Este pedido não tem nenhuma oferta para aceitar")
    if hold.hold_expires_at <= now:
        hold.status, hold.cancelled_at, hold.version = "CANCELLED", now, hold.version + 1
        waitlist.release(db, hold, now, entry_status="EXPIRED")
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "A oferta expirou e o horário passou ao seguinte da fila")

    hold.status, hold.hold_expires_at, hold.version = "CONFIRMED", None, hold.version + 1
    entry.status, entry.version = "ACCEPTED", entry.version + 1
    db.add(
        Notification(
            user_id=hold.user_id,
            recipient_email=hold.user_email,
            type="RESERVATION_CREATED",
            reservation_id=hold.id,
            payload={
                "resource_name": hold.resource_name,
                "start_at": hold.start_at.isoformat(),
                "end_at": hold.end_at.isoformat(),
            },
        )
    )
    db.commit()
    db.refresh(hold)

    log.info("fila_aceite user_id=%s entrada_id=%s reserva_id=%s", user.id, entry.id, hold.id)
    return hold


@router.post("/{entry_id}/sair", response_model=WaitlistOut)
def leave_waitlist(
    entry_id: uuid.UUID,
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> WaitlistOut:
    """Sai da fila. Se já tinha uma oferta, é uma recusa: a reserva HELD é cancelada e o horário passa ao seguinte."""
    entry = _get_own(db, entry_id, user)
    now = datetime.now(timezone.utc)

    if entry.status == "OFFERED":
        hold = db.scalars(
            select(Reservation).where(Reservation.id == entry.reservation_id).with_for_update(of=Reservation)
        ).one()
        _lock(db, entry)
        if entry.status == "OFFERED" and hold.status == "HELD":
            hold.status, hold.cancelled_at, hold.version = "CANCELLED", now, hold.version + 1
            waitlist.release(db, hold, now)  # o pedido passa a CANCELLED e o horário vai para o seguinte
            db.commit()
            db.refresh(entry)
            log.info("fila_recusa user_id=%s entrada_id=%s", user.id, entry.id)
            return _out(db, entry)

    _lock(db, entry)
    if entry.status != "WAITING":
        raise HTTPException(status.HTTP_409_CONFLICT, "Este pedido já não está na fila")
    entry.status, entry.version = "CANCELLED", entry.version + 1
    db.commit()
    db.refresh(entry)

    log.info("fila_saida user_id=%s entrada_id=%s", user.id, entry.id)
    return _out(db, entry)