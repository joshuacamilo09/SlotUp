"""Mapeia as tabelas do booking_db criadas pelas migrações do Alembic.

As migrações (alembic/versions/) são a fonte de verdade do schema: aqui só
mapeamos as colunas para objetos Python. As restrições (CHECK, índices únicos,
constraint contra sobreposição) vivem só nas migrações, porque quem as garante
é o próprio PostgreSQL. Se uma migração mudar colunas, atualize este ficheiro.
"""
import uuid
from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, SmallInteger, String, Text, Time, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Category(Base):
    """Tabela `categories` (migrações 0001 e 0005)."""

    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AvailabilityRule(Base):
    """Tabela `availability_rules` (migração 0001): um intervalo de abertura num dia da semana.

    weekday segue o Python: 0 = segunda-feira ... 6 = domingo. Um recurso pode ter
    mais do que um intervalo no mesmo dia (ex.: 09:00-13:00 e 14:00-18:00).
    """

    __tablename__ = "availability_rules"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    resource_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("resources.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(SmallInteger)
    open_time: Mapped[time] = mapped_column(Time)
    close_time: Mapped[time] = mapped_column(Time)


class Resource(Base):
    """Tabela `resources` (migração 0001): mesa, sala, vaga, quadra de padel..."""

    __tablename__ = "resources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())
    category_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(String(150))
    resource_type: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, server_default="1")
    attributes: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    category: Mapped[Category] = relationship(lazy="joined", innerjoin=True)
    # passive_deletes: ao apagar um recurso, quem apaga as regras é o ON DELETE CASCADE do PostgreSQL
    rules: Mapped[list[AvailabilityRule]] = relationship(
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=(AvailabilityRule.weekday, AvailabilityRule.open_time),
    )

    # Nomes usados nas respostas da API (ver ResourceOut em schemas.py)
    @property
    def category_name(self) -> str:
        return self.category.name

    @property
    def schedule(self) -> list[AvailabilityRule]:
        return self.rules