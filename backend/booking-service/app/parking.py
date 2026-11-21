"""Limite de 1 vaga de estacionamento por utilizador e por dia.

* "Dia" é o dia local do complexo (LOCAL_TIMEZONE), não o dia em UTC.
* Conta as reservas HELD e CONFIRMED em recursos da categoria PARKING_CATEGORY.
  Uma reserva cancelada deixa de contar: cancelar liberta a vaga do dia.
* Corre na mesma transação que grava a reserva. Antes de contar, pede um
  "advisory lock" ao PostgreSQL para este utilizador e este dia: se chegarem dois
  pedidos do mesmo utilizador ao mesmo tempo (até em réplicas diferentes), o
  segundo espera pelo commit do primeiro e já o vê. Sem o lock, os dois podiam
  contar zero e passar os dois.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Category, Reservation, Resource

ONE_PER_DAY = "Já tem uma vaga de estacionamento reservada neste dia. Cancele-a primeiro para reservar outra."


def is_parking(resource: Resource, settings: Settings) -> bool:
    return resource.category.name.strip().casefold() == settings.parking_category.strip().casefold()


def check_one_per_day(db: Session, user_id, resource: Resource, start: datetime, settings: Settings,
                      ignore_id=None) -> None:
    """Lança 409 se o utilizador já tiver outra vaga ativa no mesmo dia local.

    ignore_id: a reserva que está a ser confirmada (ao aceitar uma oferta da fila,
    a própria reserva HELD não conta como "outra vaga").
    """
    if not is_parking(resource, settings):
        return

    tz = ZoneInfo(settings.local_timezone)
    day = start.astimezone(tz).date()
    day_start = datetime.combine(day, time(0), tzinfo=tz)
    day_end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=tz)

    # Um lock por (utilizador, dia), libertado sozinho no commit ou no rollback
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"vaga:{user_id}:{day.isoformat()}"))))

    query = (
        select(Reservation.id)
        .join(Resource, Reservation.resource_id == Resource.id)
        .join(Category, Resource.category_id == Category.id)
        .where(
            Reservation.user_id == user_id,
            Reservation.status.in_(("HELD", "CONFIRMED")),
            Reservation.start_at >= day_start,
            Reservation.start_at < day_end,
            func.lower(func.trim(Category.name)) == settings.parking_category.strip().lower(),
        )
        .limit(1)
    )
    if ignore_id is not None:
        query = query.where(Reservation.id != ignore_id)
    if db.scalar(query) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, ONE_PER_DAY)
