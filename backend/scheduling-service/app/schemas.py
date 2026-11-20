"""Contrato de dados booking -> scheduling (validado pelo Pydantic).

É a versão em código do documentacao/README.md: se um mudar, o
outro tem de mudar também. O booking monta este corpo a partir do booking_db.
"""
from datetime import date, datetime
from typing import Annotated, Literal  # Literal: o campo só aceita os valores listados

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

# Hora "HH:MM" ou "HH:MM:00" (o booking manda com segundos). (:00)? = os segundos são opcionais
Hora = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d(:00)?$")]
Id = Annotated[str, StringConstraints(min_length=1, max_length=64)]
# Igual ao booking: "Mesa" e "mesa" ficam iguais (to_lower) e os espaços à volta saem
ResourceType = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=2, max_length=30)]


class Strict(BaseModel):
    """Base de todos os modelos de ENTRADA: campo desconhecido dá 422 em vez de ser ignorado."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- entrada
class Activity(Strict):
    """Uma atividade pedida pelo usuário (uma variável do CSP)."""

    id: Id
    resource_type: ResourceType
    people: int = Field(ge=1)  # obrigatório: sem valor por padrão
    # multiple_of=15: a mesma grelha de 15 min do booking
    duration_min: int | None = Field(default=None, ge=15, multiple_of=15)
    preferred_start: Hora | None = None
    # Janela preferida: a atividade inteira deve caber entre preferred_start e preferred_end.
    # Sem preferred_end, a janela é preferred_start + duração (uma "hora específica")
    preferred_end: Hora | None = None
    covers_day: bool = False
    favorite_resource_id: Id | None = None  # preenchido pelo booking a partir do histórico (F3)

    # mode="after": corre depois de os campos já estarem validados um a um
    @model_validator(mode="after")
    def _campos_conforme_o_tipo(self) -> "Activity":
        if self.covers_day:
            # A vaga não tem horário próprio: a VAGA_COBRE_O_DIA calcula-o a partir das outras atividades
            if self.duration_min is not None or self.preferred_start is not None or self.preferred_end is not None:
                raise ValueError(f"'{self.id}': uma atividade que cobre o dia não leva duração nem horário preferido")
        elif self.duration_min is None or self.preferred_start is None:
            raise ValueError(f"'{self.id}': duration_min e preferred_start são obrigatórios")
        elif self.preferred_end is not None and self.preferred_end <= self.preferred_start:
            raise ValueError(f"'{self.id}': preferred_end tem de ser depois de preferred_start")
        return self

class ScheduleRule(Strict):
    """Um intervalo do horário SEMANAL do recurso (igual ao availability_rules do booking)."""

    weekday: int = Field(ge=0, le=6)  # 0 = segunda ... 6 = domingo (convenção do Python)
    open_time: Hora
    close_time: Hora

    @model_validator(mode="after")
    def _fecha_depois_de_abrir(self) -> "ScheduleRule":
        if self.close_time <= self.open_time:
            raise ValueError("close_time tem de ser depois de open_time")
        return self


# Os mesmos limites da migração 0007 do booking
DurationMin = Annotated[int, Field(ge=15, le=1440, multiple_of=15)]
BufferMin = Annotated[int, Field(ge=0, le=60)]


class ResourceIn(Strict):
    """Um recurso ativo candidato, com as SUAS regras (os nomes são os do ResourceOut do booking)."""

    id: Id
    name: Annotated[str, StringConstraints(min_length=1, max_length=150)]
    resource_type: ResourceType
    capacity: int = Field(ge=1)
    schedule: Annotated[list[ScheduleRule], Field(max_length=35)]  # 7 dias x 5 intervalos, como no booking
    min_duration_min: DurationMin
    max_duration_min: DurationMin
    buffer_min: BufferMin

    @model_validator(mode="after")
    def _minimo_ate_maximo(self) -> "ResourceIn":
        if self.min_duration_min > self.max_duration_min:
            raise ValueError(f"'{self.id}': min_duration_min não pode ser maior que max_duration_min")
        return self

class BusyInterval(Strict):
    """Um intervalo ocupado por uma reserva CONFIRMED ou HELD."""

    resource_id: Id
    start: Hora
    end: Hora

    @model_validator(mode="after")
    def _fim_depois_do_inicio(self) -> "BusyInterval":
        if self.end <= self.start:
            raise ValueError("end tem de ser depois de start")
        return self


Mode = Literal["plan", "suggest"]


class PlanIn(Strict):
    """Corpo de POST /api/scheduling/plan."""

    mode: Mode
    day: date
    now: datetime  # hora local do complexo: o scheduling não usa o relógio dele
    max_alternatives: int = Field(default=3, ge=1, le=10)  # só conta no modo suggest
    # Entre 1 e 10 atividades: limita o tamanho do problema (e o tempo de busca)
    activities: Annotated[list[Activity], Field(min_length=1, max_length=10)]
    resources: list[ResourceIn]
    busy: list[BusyInterval]

    @field_validator("now")
    @classmethod  # o field_validator recebe a classe, não um objeto já criado
    def _sem_fuso(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            raise ValueError("now vai em hora local do complexo, sem fuso (ex.: 2026-12-09T15:30)")
        return value

    @model_validator(mode="after")
    def _regras_do_pedido(self) -> "PlanIn":
        ids = [a.id for a in self.activities]
        if len(ids) != len(set(ids)):  # um set não tem repetidos: se encolheu, havia ids iguais
            raise ValueError("Os ids das atividades têm de ser únicos")
        # sum() de booleanos conta os True (True vale 1)
        if sum(a.covers_day for a in self.activities) > 1:
            raise ValueError("No máximo 1 atividade que cobre o dia (R8)")
        if self.activities and all(a.covers_day for a in self.activities):
            # A vaga cobre "da primeira à última atividade": sozinha, não há o que cobrir
            raise ValueError("O estacionamento precisa de pelo menos uma atividade com horário")
        if self.mode == "suggest" and (len(self.activities) != 1 or self.activities[0].covers_day):
            raise ValueError("mode=suggest exige exatamente 1 atividade, sem covers_day")
        return self


# --------------------------------------------------------------------------- saída
class PlanItem(BaseModel):
    """Uma atividade já decidida: que recurso, de quando a quando."""

    activity_id: str
    resource_id: str
    resource_name: str
    start: str
    end: str


class Solution(BaseModel):
    """Um plano completo (modo plan) ou uma sugestão (modo suggest)."""

    cost: float
    items: list[PlanItem]


FailureCode = Literal[
    "NO_RESOURCE", "NO_CAPACITY", "NO_FREE_SLOT", "CONFLICT", "PARKING_NOT_COVERED", "LIMIT_REACHED"
]


class Reason(BaseModel):
    """Porque é que UM recurso não serve para a atividade que falhou."""
    rule_id: str              # a regra que o tirou de jogo (ex.: "CAPACIDADE")
    resource_id: str
    message: str              # texto pronto para a tela (ex.: "Sala Pequena: só tem lugar para 4 ...")


class Failure(BaseModel):
    code: FailureCode
    activity_id: str | None
    rule_id: str | None  # a regra que impediu o plano (ex.: "DURACAO"); None quando não há uma só
    message: str
    reasons: list[Reason] = []  # um por recurso do tipo pedido; vazio quando a falha é da combinação


class PlanStats(BaseModel):
    """Números da busca."""

    nodes: int
    solutions: int
    prunes: int
    time_ms: float
    limit_reached: bool


class PlanOut(BaseModel):
    """Resposta: só um de plan, alternatives e failure vem preenchido; os outros vêm null."""

    status: Literal["OK", "NO_SOLUTION"]
    mode: Mode
    plan: Solution | None
    alternatives: list[Solution] | None
    failure: Failure | None
    stats: PlanStats