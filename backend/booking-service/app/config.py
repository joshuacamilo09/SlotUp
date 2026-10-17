"""Configuração do booking-service (variáveis de ambiente)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    service_name: str = "booking-service"

    db_host: str = "db"
    db_port: int = 5432
    db_name: str = "booking_db"
    db_user: str = "booking_user"
    db_password: str

    # Só a chave PÚBLICA: este serviço consegue validar tokens, mas nunca criar um.
    jwt_public_key_file: str = "/run/secrets/jwt_public_key"
    jwt_issuer: str = "slotup-auth"
    jwt_audience: str = "slotup"

    # Chamado mais tarde pelo fluxo de reservas (Sprint 3)
    scheduling_url: str = "http://scheduling:8003"

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
