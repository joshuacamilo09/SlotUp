"""Mapeia a tabela `users` criada pela migração do Alembic
(alembic/versions/0001_create_users.py).

A migração é a fonte de verdade do schema: aqui só mapeamos as colunas
para objetos Python. As restrições (CHECK, índice único do email) vivem
só na migração, porque quem as garante é o próprio PostgreSQL.
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, LargeBinary, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(10), default="USER")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    two_fa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_secret_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    totp_last_used_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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