"""Mapeia as tabelas do booking_db criadas pelas migrações do Alembic.

As migrações (alembic/versions/) são a fonte de verdade do schema: aqui só
mapeamos as colunas para objetos Python. As restrições (CHECK, índices únicos,
constraint contra sobreposição) vivem só nas migrações, porque quem as garante
é o próprio PostgreSQL. Se uma migração mudar colunas, atualize este ficheiro.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

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