"""Formatos de entrada e saída da API (validados pelo Pydantic)."""
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

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