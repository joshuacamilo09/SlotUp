"""Configuração do booking-service.

Tudo vem de variáveis de ambiente (12-factor). Os valores abaixo são só os de
omissão; quem manda é o ambiente:
  * Docker Compose: infra/docker/config/booking.env (configuração) e .env (senha)
  * Kubernetes: ConfigMap booking-config e Secrets (infra/k8s/)
"""
import socket
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    service_name: str = "booking-service"

    # Nome desta réplica (booking1, booking2...). No Compose vem de INSTANCE_NAME;
    # sem a variável, fica o hostname do contentor.
    instance_name: str = socket.gethostname()

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

    # Fuso horário do complexo. O horário de funcionamento (availability_rules) está
    # em hora local, enquanto o banco guarda as reservas em UTC (timestamptz).
    local_timezone: str = "Europe/Lisbon"

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
