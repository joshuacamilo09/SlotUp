"""Formatos de entrada e saída da API (validados pelo Pydantic)."""
import json
import uuid
from collections import defaultdict
from datetime import datetime, time
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

# strip_whitespace: " Coworking " é guardado como "Coworking"
CategoryName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
CategoryDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class CategoryCreate(BaseModel):
    # extra="forbid": um campo desconhecido (ex.: "is_admin") dá 422 em vez de ser ignorado
    model_config = ConfigDict(extra="forbid")

    name: CategoryName
    description: CategoryDescription | None = None


class CategoryUpdate(BaseModel):
    """PATCH: só os campos enviados são alterados."""

    model_config = ConfigDict(extra="forbid")

    name: CategoryName | None = None
    description: CategoryDescription | None = None  # enviar null apaga a descrição
    is_active: bool | None = None  # false = desativar (não se apaga, ver routers/categories.py)

    @model_validator(mode="after")
    def _check(self) -> "CategoryUpdate":
        sent = self.model_fields_set
        if not sent:
            raise ValueError("Envie pelo menos um campo para alterar")
        if "name" in sent and self.name is None:
            raise ValueError("O nome não pode ser null")
        if "is_active" in sent and self.is_active is None:
            raise ValueError("is_active não pode ser null")
        return self


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- recursos
ResourceName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)]
# to_lower: "Mesa" e "mesa" ficam iguais, para o filtro e as estatísticas não se dividirem
ResourceType = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=2, max_length=30)]
ResourceDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]

DEFAULT_OPEN = time(8, 0)
DEFAULT_CLOSE = time(20, 0)


def _small_json(value: dict) -> dict:
    # `attributes` é um saco de extras (ex.: {"tem_projetor": true}); não deixamos crescer sem limite
    if len(json.dumps(value)) > 4000:
        raise ValueError("attributes é demasiado grande (máx. 4000 caracteres em JSON)")
    return value


Attributes = Annotated[dict[str, Any], AfterValidator(_small_json)]


class AvailabilityRuleIn(BaseModel):
    """Um intervalo em que o recurso está aberto. weekday: 0 = segunda ... 6 = domingo."""

    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(ge=0, le=6)
    open_time: time
    close_time: time

    @field_validator("open_time", "close_time")
    @classmethod
    def _no_timezone(cls, value: time) -> time:
        # A coluna é `time` sem fuso: a hora é a hora local do complexo
        if value.tzinfo is not None:
            raise ValueError("Use horas sem fuso horário (ex.: 08:00)")
        return value

    @model_validator(mode="after")
    def _close_after_open(self) -> "AvailabilityRuleIn":
        if self.close_time <= self.open_time:
            raise ValueError("close_time tem de ser depois de open_time")
        return self


def _no_overlaps(rules: list[AvailabilityRuleIn]) -> list[AvailabilityRuleIn]:
    by_day: dict[int, list[AvailabilityRuleIn]] = defaultdict(list)
    for rule in rules:
        by_day[rule.weekday].append(rule)
    for weekday, items in by_day.items():
        items.sort(key=lambda r: r.open_time)
        for previous, following in zip(items, items[1:]):
            if following.open_time < previous.close_time:
                raise ValueError(f"Intervalos sobrepostos no dia {weekday}")
    return rules


# máx. 35 = 7 dias x 5 intervalos
Schedule = Annotated[list[AvailabilityRuleIn], Field(max_length=35), AfterValidator(_no_overlaps)]


def default_schedule() -> list[AvailabilityRuleIn]:
    """Horário de um recurso novo, se o admin não indicar nenhum: todos os dias, 08:00-20:00."""
    return [AvailabilityRuleIn(weekday=day, open_time=DEFAULT_OPEN, close_time=DEFAULT_CLOSE) for day in range(7)]


class ResourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID
    name: ResourceName
    resource_type: ResourceType
    description: ResourceDescription | None = None
    capacity: int = Field(default=1, ge=1, le=1000)
    attributes: Attributes = Field(default_factory=dict)
    # None (não enviado) = horário por defeito; [] = recurso sem horário (nunca abre)
    schedule: Schedule | None = None


class ResourceUpdate(BaseModel):
    """PATCH: só os campos enviados são alterados. O horário altera-se em PUT /{id}/horarios."""

    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID | None = None
    name: ResourceName | None = None
    resource_type: ResourceType | None = None
    description: ResourceDescription | None = None  # enviar null apaga a descrição
    capacity: int | None = Field(default=None, ge=1, le=1000)
    attributes: Attributes | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _check(self) -> "ResourceUpdate":
        sent = self.model_fields_set
        if not sent:
            raise ValueError("Envie pelo menos um campo para alterar")
        for field in ("category_id", "name", "resource_type", "capacity", "attributes", "is_active"):
            if field in sent and getattr(self, field) is None:
                raise ValueError(f"{field} não pode ser null")
        return self


class ScheduleReplace(BaseModel):
    """PUT /{id}/horarios: substitui o horário inteiro."""

    model_config = ConfigDict(extra="forbid")

    rules: Schedule


class AvailabilityRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weekday: int
    open_time: time
    close_time: time


class ResourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    category_name: str
    name: str
    resource_type: str
    description: str | None
    capacity: int
    attributes: dict[str, Any]
    is_active: bool
    schedule: list[AvailabilityRuleOut]
    created_at: datetime
    updated_at: datetime


class ResourceDeleteOut(BaseModel):
    """Resultado do DELETE: apagado de vez, ou só desativado (porque já tem reservas)."""

    action: Literal["deleted", "deactivated"]
    resource_id: uuid.UUID