"""Disponibilidade de um recurso num dia: quando abre, o que está ocupado e o que está livre.

GET /api/reservas/recursos/{resource_id}/disponibilidade?day=AAAA-MM-DD

* Qualquer usuário autenticado consulta recursos ativos (de categorias ativas); o ADMIN vê todos.
* Ocupado = reservas HELD ou CONFIRMED, os mesmos estados que a constraint do banco bloqueia.
  Assim, um horário que aparece como livre é um horário que o banco aceita.
* Nunca revela quem reservou: só os horários.
* As horas que já passaram não aparecem como livres.
"""

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import Reservation, Resource
from app.schemas import AvailabilityOut, TimeInterval
from app.security import CurrentUser, current_user

router = APIRouter(prefix="/api/reservas/recursos", tags=["disponibilidade"])

# Os mesmos estados da constraint reservations_no_overlap (migração 0002)
BLOCKING_STATUSES = ("HELD", "CONFIRMED")

# Um intervalo é um par (início, fim). "tuple[...]" só documenta o tipo para quem lê.
Interval = tuple[datetime, datetime]

def _subtract(opening: list[Interval], taken: list[Interval]) -> list[Interval]:
    """Devolve as partes dos intervalos de abertura que não estão ocupadas.

    Ex.: abertura 08:00-20:00, ocupado 10:00-11:00 -> livre 08:00-10:00 e 11:00-20:00.
    """
    taken = sorted(taken) # ordena por início, para percorrer da esquerda para a direita
    free: list[Interval] = []
    for start, end in sorted(opening):
        cursor = start # até onde já sabemos o que está livre ou ocupado
        for taken_start, taken_end in taken:
            if taken_end <= cursor or taken_start >= end:
                continue # este ocupado não toca no pedaço que falta analisar
            if taken_start > cursor:
                free.append((cursor, taken_start)) # o espaço antes do ocupado está livre
            cursor = max(cursor, taken_end) # salta para o fim do ocupado
            if cursor >= end:
                break
        if cursor < end:
            free.append((cursor, end)) # o que sobra até ao fecho está livre
    return free

@router.get("/{resource_id}/disponibilidade", response_model=AvailabilityOut)
def get_availability(
    resource_id: uuid.UUID,
    day: date = Query(..., description="Dia a consultar (AAAA-MM-DD), na hora local do complexo"),
    user: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AvailabilityOut:
    # Mesma regra de visibilidade das rotas de recursos: inativo = invisível para o usuário comum
    resource = db.get(Resource, resource_id)
    hidden = resource is not None and user.role != "ADMIN" and not (resource.is_active and resource.category.is_active)
    if resource is None or hidden:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurso não encontrado")

    tz = ZoneInfo(settings.local_timezone)
    # O dia vai da meia-noite local à meia-noite local seguinte. Com o fuso, o Python
    # trata sozinho os dias de mudança de hora (23 ou 25 horas).
    day_start = datetime.combine(day, time.min, tzinfo=tz)
    day_end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)

    # Abertura: as regras do dia da semana (0 = segunda, igual ao date.weekday() do Python)
    opening = [
        (datetime.combine(day, rule.open_time, tzinfo=tz), datetime.combine(day, rule.close_time, tzinfo=tz))
        for rule in resource.rules
        if rule.weekday == day.weekday()
    ]

    # Ocupado: reservas que tocam no dia (começam antes do fim do dia e acabam depois do início)
    rows = db.execute(
        select(Reservation.start_at, Reservation.end_at)
        .where(
            Reservation.resource_id == resource_id,
            Reservation.status.in_(BLOCKING_STATUSES),
            Reservation.start_at < day_end,
            Reservation.end_at > day_start,
        )
        .order_by(Reservation.start_at)
    ).all()
    # O banco devolve em UTC: converte para a hora local e corta ao limite do dia
    busy = [(max(start.astimezone(tz), day_start), min(end.astimezone(tz), day_end)) for start, end in rows]

    # O passado conta como "ocupado" no cálculo, mas não aparece na lista busy
    now = datetime.now(tz)
    past = [(day_start, min(now, day_end))] if now > day_start else []
    free = _subtract(opening, busy + past)

    def as_out(intervals: list[Interval]) -> list[TimeInterval]:
        return [TimeInterval(start=start, end=end) for start, end in intervals]

    return AvailabilityOut(
        resource_id=resource_id,
        day=day,
        timezone=settings.local_timezone,
        opening=as_out(sorted(opening)),
        busy=as_out(busy),
        free=as_out(free),
    )