"""Formatos de entrada e saída da API do scheduling (validados pelo Pydantic).

A entrada tem o mesmo formato dos cenários em dados/. Na 3ª entrega é o booking
que vai montar este corpo a partir do booking_db.
"""
from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Hora "HH:MM" de 00:00 a 23:59. O pattern é uma expressão regular:
# [01]\d = 00 a 19, 2[0-3] = 20 a 23, [0-5]\d = 00 a 59
Hora = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


# --------------------------------------------------------------------------- entrada
class PlanRequestItem(BaseModel):
    """Um serviço pedido pelo usuário (uma variável do CSP)."""

    model_config = ConfigDict(extra="forbid")  # campo desconhecido dá 422

    id: Annotated[str, StringConstraints(min_length=1, max_length=50)]
    resource_type: str
    desired_start: Hora | None = None
    duration_min: int | None = Field(default=None, gt=0)  # gt=0: maior que zero
    people: int = Field(default=1, ge=1)
    favorite_resource_id: str | None = None
    covers_day: bool = False


class OpeningWindow(BaseModel):
    """Uma janela de abertura do recurso NAQUELE dia."""

    open_time: Hora
    close_time: Hora


class PlanResource(BaseModel):
    """Um recurso candidato (os mesmos nomes de campos do ResourceOut do booking)."""

    id: str
    name: str
    resource_type: str
    capacity: int = Field(ge=1)
    schedule: list[OpeningWindow]


class BusyInterval(BaseModel):
    """Um intervalo já ocupado (reservas CONFIRMED ou HELD)."""

    resource_id: str
    start: Hora
    end: Hora


class PlanIn(BaseModel):
    """Corpo de POST /api/scheduling/plan."""

    model_config = ConfigDict(extra="forbid")

    day: date
    # Entre 1 e 10 pedidos: limita o tamanho do problema (e o tempo de busca)
    requests: Annotated[list[PlanRequestItem], Field(min_length=1, max_length=10)]
    resources: list[PlanResource]
    busy: list[BusyInterval] = []


# --------------------------------------------------------------------------- saída
class PlanItemOut(BaseModel):
    """Um serviço já decidido: que recurso, de quando a quando."""

    request_id: str
    resource_id: str
    resource_name: str
    start: str | None
    end: str | None


class PlanStats(BaseModel):
    """Números da busca (úteis na demo e no relatório)."""

    nodes: int
    solutions: int
    prunes: int
    time_ms: float
    limit_reached: bool  # True = a busca parou no limite; a solução pode não ser a ótima


class PlanOut(BaseModel):
    """Resposta: OK com o dia planeado, ou NO_SOLUTION se não houver combinação possível."""

    status: str
    cost: float | None
    items: list[PlanItemOut]
    stats: PlanStats