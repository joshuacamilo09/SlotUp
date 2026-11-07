"""Regras da fila de espera, partilhadas pelas rotas e pelo job de expiração.

Como funciona:
1. Alguém quer um horário ocupado e entra na fila (WAITING).
2. A reserva que ocupava o horário é cancelada (ou uma oferta expira ou é recusada):
   release() chama offer_freed_slot(), que percorre a fila por ordem de chegada.
3. O primeiro da fila cujo horário ficou livre recebe uma OFERTA: uma reserva HELD,
   guardada só para ele durante HOLD_MINUTES. Ninguém mais consegue reservar esse
   horário, porque a constraint reservations_no_overlap também conta HELD.
4. Ele aceita (HELD -> CONFIRMED) ou recusa/deixa expirar (HELD -> CANCELLED) e
   o horário passa ao seguinte da fila.

Tudo corre dentro da transação de quem chama: o commit é feito pela rota (ou pelo job).
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Notification, Reservation, WaitlistEntry

log = logging.getLogger("booking.waitlist")

# Tempo que a oferta fica guardada para o primeiro da fila
HOLD_MINUTES = 15


def offer_freed_slot(db: Session, resource_id, start: datetime, end: datetime, now: datetime) -> int:
    """O horário [start, end) deste recurso ficou livre: oferece-o à fila. Devolve quantas ofertas fez.

    * Ordem de chegada (created_at). Só entram pedidos que se sobrepõem ao horário libertado.
    * FOR UPDATE SKIP LOCKED: se outra transação (outra réplica) já está a tratar um pedido
      da fila, este é saltado em vez de ficar à espera. Nunca há duas ofertas para o mesmo pedido.
    * Cada oferta é um INSERT HELD dentro de um SAVEPOINT. Se o horário pedido ainda estiver
      ocupado por outra reserva, a constraint recusa, o savepoint desfaz só essa tentativa e
      passa-se ao pedido seguinte. Assim, um horário libertado grande pode servir vários pedidos
      pequenos, e um pedido maior do que o horário libertado fica à espera.
    """
    entries = db.scalars(
        select(WaitlistEntry)
        .where(
            WaitlistEntry.resource_id == resource_id,
            WaitlistEntry.status == "WAITING",
            WaitlistEntry.desired_start < end,
            WaitlistEntry.desired_end > start,
        )
        .order_by(WaitlistEntry.created_at, WaitlistEntry.id)
        .with_for_update(of=WaitlistEntry, skip_locked=True)
    ).all()

    offers = 0
    for entry in entries:
        if entry.desired_start <= now:
            entry.status = "EXPIRED"  # o horário pedido já começou: já não vale a pena oferecer
            continue

        hold = Reservation(
            user_id=entry.user_id,
            user_email=entry.user_email,
            resource_id=entry.resource_id,
            start_at=entry.desired_start,
            end_at=entry.desired_end,
            status="HELD",
            # Nunca guarda para além do início da própria reserva
            hold_expires_at=min(now + timedelta(minutes=HOLD_MINUTES), entry.desired_start),
        )
        try:
            with db.begin_nested():  # SAVEPOINT
                db.add(hold)
                db.flush()
        except IntegrityError:
            continue  # ainda ocupado por outra reserva: fica WAITING

        entry.status = "OFFERED"
        entry.reservation_id = hold.id
        entry.version += 1
        db.add(
            Notification(
                user_id=entry.user_id,
                recipient_email=entry.user_email,
                type="WAITLIST_OFFERED",
                reservation_id=hold.id,
                waitlist_entry_id=entry.id,
                payload={
                    "resource_name": entry.resource_name,
                    "start_at": entry.desired_start.isoformat(),
                    "end_at": entry.desired_end.isoformat(),
                    "hold_expires_at": hold.hold_expires_at.isoformat(),
                },
            )
        )
        offers += 1
        log.info("fila_oferta entrada_id=%s reserva_id=%s", entry.id, hold.id)
    return offers


def release(db: Session, reservation: Reservation, now: datetime, entry_status: str = "CANCELLED") -> int:
    """A reserva acabou de passar a CANCELLED: fecha a oferta da fila (se era uma) e passa o horário à fila.

    entry_status: CANCELLED quando a pessoa recusa ou cancela; EXPIRED quando o prazo da oferta acabou.
    """
    entry = db.scalars(
        select(WaitlistEntry)
        .where(WaitlistEntry.reservation_id == reservation.id, WaitlistEntry.status == "OFFERED")
        .with_for_update(of=WaitlistEntry)
    ).first()
    if entry is not None:
        entry.status = entry_status
        entry.version += 1
    db.flush()  # o horário fica livre já, dentro desta transação, antes de procurar o seguinte
    return offer_freed_slot(db, reservation.resource_id, reservation.start_at, reservation.end_at, now)


def expire(db: Session, now: datetime) -> tuple[int, int]:
    """Fecha o que passou do prazo. Devolve (ofertas expiradas, pedidos expirados).

    * Ofertas (reservas HELD) com hold_expires_at no passado: a reserva passa a CANCELLED,
      o pedido a EXPIRED, e o horário passa ao seguinte da fila.
    * Pedidos WAITING cujo horário já começou: EXPIRED.
    Corre pelo job app/expire_holds.py (CronJob no Kubernetes) e também antes de aceitar uma oferta.
    """
    holds = db.scalars(
        select(Reservation)
        .where(Reservation.status == "HELD", Reservation.hold_expires_at <= now)
        .order_by(Reservation.hold_expires_at)
        .with_for_update(of=Reservation, skip_locked=True)
    ).all()
    for hold in holds:
        hold.status = "CANCELLED"
        hold.cancelled_at = now
        hold.version += 1
        release(db, hold, now, entry_status="EXPIRED")

    stale = db.scalars(
        select(WaitlistEntry)
        .where(WaitlistEntry.status == "WAITING", WaitlistEntry.desired_start <= now)
        .with_for_update(of=WaitlistEntry, skip_locked=True)
    ).all()
    for entry in stale:
        entry.status = "EXPIRED"
    return len(holds), len(stale)


def queue_position(db: Session, entry: WaitlistEntry) -> int | None:
    """Posição na fila (1 = o próximo) entre os pedidos WAITING que disputam o mesmo horário."""
    if entry.status != "WAITING":
        return None
    ahead = db.scalars(
        select(WaitlistEntry.id).where(
            WaitlistEntry.resource_id == entry.resource_id,
            WaitlistEntry.status == "WAITING",
            WaitlistEntry.desired_start < entry.desired_end,
            WaitlistEntry.desired_end > entry.desired_start,
            or_(
                WaitlistEntry.created_at < entry.created_at,
                and_(WaitlistEntry.created_at == entry.created_at, WaitlistEntry.id < entry.id),
            ),
        )
    ).all()
    return len(ahead) + 1