"""Formato do contrato booking ⇄ scheduling (validado pelo Pydantic).

As descrições (description=...) e os docstrings das classes aparecem no Swagger (/docs).
O contrato completo, com exemplos, está no README.md do serviço.
"""
from datetime import date, datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Hora = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d(:00)?$")]
Id = Annotated[str, StringConstraints(min_length=1, max_length=64)]
ResourceType = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=2, max_length=30)]

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Activity(Strict):
    """Uma atividade do dia: uma variável do CSP."""

    id: Id = Field(description="Nome único da atividade no pedido (volta no activity_id da resposta).")
    resource_type: ResourceType = Field(description="Tipo de recurso, igual ao do booking (mesa, sala, quadra, personal, vaga_carro, vaga_mota).")
    people: int = Field(ge=1, description="Número de pessoas. O recurso precisa de capacity maior ou igual (regra CAPACIDADE).")
    duration_min: int | None = Field(default=None, ge=15, multiple_of=15,
                                     description="Duração em minutos, múltiplo de 15. Obrigatória, exceto com covers_day.")
    preferred_start: Hora | None = Field(default=None, description="Início da janela preferida (HH:MM). Obrigatório, exceto com covers_day.")
    # Janela preferida: a atividade inteira deve caber entre preferred_start e preferred_end.
    # Sem preferred_end, a janela é preferred_start + duração (uma "hora específica")
    preferred_end: Hora | None = Field(default=None, description="Fim da janela preferida (ex.: manhã = 08:00 a 13:00). Sem ele, a janela é preferred_start + duração. Cada minuto fora custa 1 ponto (F1).")
    covers_day: bool = Field(default=False, description="Só nas vagas: a vaga cobre da 1.ª à última atividade, com 10 min de folga, arredondado a 15 min.")
    favorite_resource_id: Id | None = Field(default=None, description="Recurso preferido (o booking preenche pelo histórico). Não ficar com ele custa 30 pontos (F3).")
    @model_validator(mode="after")
    def _campos_conforme_o_tipo(self) -> "Activity":
        if self.covers_day:
            if self.duration_min is not None or self.preferred_start is not None or self.preferred_end is not None:
                raise ValueError(f"'{self.id}': uma atividade que cobre o dia não leva duração nem horário preferido")
        elif self.duration_min is None or self.preferred_start is None:
            raise ValueError(f"'{self.id}': duration_min e preferred_start são obrigatórios")
        elif self.preferred_end is not None and self.preferred_end <= self.preferred_start:
            raise ValueError(f"'{self.id}': preferred_end tem de ser depois de preferred_start")
        return self

class ScheduleRule(Strict):
    """Um intervalo do horário SEMANAL do recurso (igual ao availability_rules do booking)."""

    weekday: int = Field(ge=0, le=6, description="0 = segunda ... 6 = domingo (convenção do Python).")
    open_time: Hora = Field(description="Abre (HH:MM ou HH:MM:SS, hora local).")
    close_time: Hora = Field(description="Fecha (HH:MM ou HH:MM:SS, hora local).")

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
    capacity: int = Field(ge=1, description="Quantas pessoas cabem.")
    # 7 dias x 5 intervalos, como no booking
    schedule: Annotated[list[ScheduleRule], Field(max_length=35, description="Horário SEMANAL; o scheduling escolhe as janelas do dia pedido. Lista vazia = sempre fechado.")]
    min_duration_min: DurationMin = Field(description="Duração mínima de uma reserva (regra DURACAO).")
    max_duration_min: DurationMin = Field(description="Duração máxima de uma reserva (regra DURACAO).")
    buffer_min: BufferMin = Field(description="Intervalo obrigatório entre reservas seguidas do recurso (regra INTERVALO_RECURSO).")

    @model_validator(mode="after")
    def _minimo_ate_maximo(self) -> "ResourceIn":
        if self.min_duration_min > self.max_duration_min:
            raise ValueError(f"'{self.id}': min_duration_min não pode ser maior que max_duration_min")
        return self


class BusyInterval(Strict):
    """Um intervalo ocupado de um recurso (reservas CONFIRMED e HELD), em hora local do dia pedido."""

    resource_id: Id
    start: Hora
    end: Hora
    @model_validator(mode="after")
    def _fim_depois_do_inicio(self) -> "BusyInterval":
        if self.end <= self.start:
            raise ValueError("end tem de ser depois de start")
        return self

Mode = Literal["plan", "suggest"]

# Tamanho máximo de um pedido. 10 atividades já é um dia muito cheio (a tela permite 5);
# os outros dois só protegem o serviço de pedidos absurdos.
MAXIMOS = {"activities": 10, "resources": 300, "busy": 3000}

class PlanIn(Strict):
    """O pedido do booking: o dia, as atividades e tudo o que o CSP precisa de saber do banco."""

    mode: Mode = Field(description="plan = planear o dia inteiro; suggest = sugerir horários para UMA atividade.")
    day: date = Field(description="Dia a planear (AAAA-MM-DD).")
    now: datetime = Field(description="Agora, em hora local do complexo e SEM fuso. No dia de hoje, nada começa antes disto.")
    max_alternatives: int = Field(default=3, ge=1, le=10, description="Só no suggest: quantas sugestões devolver.")
    activities: Annotated[list[Activity], Field(min_length=1, description="As atividades pedidas (1 a 10).")]
    resources: list[ResourceIn] = Field(description="Recursos ATIVOS dos tipos pedidos (até 300).")
    busy: list[BusyInterval] = Field(description="Ocupação do dia: reservas CONFIRMED e HELD (até 3000).")

    @field_validator("activities", "resources", "busy")
    @classmethod
    def _tamanho_maximo(cls, valor: list, info) -> list:
        """Limite de tamanho do pedido, com uma mensagem clara (o 422 diz o máximo e quantos vieram)."""
        maximo = MAXIMOS[info.field_name]  # info.field_name: o campo que está a ser validado
        if len(valor) > maximo:
            raise ValueError(f"No máximo {maximo} itens em '{info.field_name}' por pedido (recebidos: {len(valor)})")
        return valor
    @field_validator("now")
    @classmethod
    def _sem_fuso(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            raise ValueError("now vai em hora local do complexo, sem fuso (ex.: 2026-12-09T15:30)")
        return value
    @model_validator(mode="after")
    def _regras_do_pedido(self) -> "PlanIn":
        ids = [a.id for a in self.activities]
        if len(ids) != len(set(ids)):
            raise ValueError("Os ids das atividades têm de ser únicos")
        if sum(a.covers_day for a in self.activities) > 1:
            raise ValueError("No máximo 1 atividade que cobre o dia (R8)")
        if self.activities and all(a.covers_day for a in self.activities):
            # A vaga cobre "da primeira à última atividade": sozinha, não há o que cobrir
            raise ValueError("O estacionamento precisa de pelo menos uma atividade com horário")
        if self.mode == "suggest" and (len(self.activities) != 1 or self.activities[0].covers_day):
            raise ValueError("mode=suggest exige exatamente 1 atividade, sem covers_day")
        return self

class PlanItem(BaseModel):
    """Uma atividade já colocada: que recurso e de quando a quando (HH:MM, hora local)."""

    activity_id: str
    resource_id: str
    resource_name: str
    start: str
    end: str

class Solution(BaseModel):
    """Um plano. cost = custo total (F1 + F2 + F3): quanto menor, mais perto do pedido."""

    cost: float
    items: list[PlanItem]

FailureCode = Literal["NO_RESOURCE", "NO_CAPACITY", "NO_FREE_SLOT", "CONFLICT", "PARKING_NOT_COVERED", "LIMIT_REACHED"]

class Reason(BaseModel):
    """Porque é que UM recurso não serve para a atividade que falhou."""
    rule_id: str              # a regra que o tirou de jogo (ex.: "CAPACIDADE")
    resource_id: str
    message: str              # texto pronto para a tela (ex.: "Sala Pequena: só tem lugar para 4 ...")


class Failure(BaseModel):
    """Porque não há plano. message e reasons já vêm em texto para a tela."""

    code: FailureCode
    activity_id: str | None
    rule_id: str | None  # a regra que impediu o plano (ex.: "DURACAO"); None quando não há uma só
    message: str
    reasons: list[Reason] = []  # um por recurso do tipo pedido; vazio quando a falha é da combinação

class PlanStats(BaseModel):
    """Números da busca: nós explorados, soluções vistas, podas do branch and bound e tempo."""

    nodes: int
    solutions: int
    prunes: int
    time_ms: float
    limit_reached: bool
    limit: Literal["nodes", "time"] | None = None  # que limite parou a busca (None = terminou)

class PlanOut(BaseModel):
    """A resposta: sempre 200 quando o pedido é válido, mesmo sem solução (status NO_SOLUTION)."""

    status: Literal["OK", "NO_SOLUTION"]
    mode: Mode
    plan: Solution | None
    alternatives: list[Solution] | None
    failure: Failure | None
    stats: PlanStats