"""Configuração do auth-service.

Tudo vem de variáveis de ambiente (12-factor). No Docker Compose são definidas
em docker-compose.yml; no Kubernetes virão de ConfigMaps e Secrets.
"""
import socket
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    service_name: str = "auth-service"

    # Nome desta réplica (auth-1, auth-2...). No Compose vem de INSTANCE_NAME;
    # sem a variável, fica o hostname do contentor.
    instance_name: str = socket.gethostname()

    # Base de dados (cada serviço só conhece a sua)
    db_host: str = "db"
    db_port: int = 5432
    db_name: str = "auth_db"
    db_user: str = "auth_user"
    db_password: str

    # JWT RS256: o auth assina com a chave privada; os outros serviços só têm a pública
    jwt_private_key_file: str = "/run/secrets/jwt_private_key"
    jwt_public_key_file: str = "/run/secrets/jwt_public_key"
    jwt_issuer: str = "slotup-auth"
    jwt_audience: str = "slotup"
    access_token_minutes: int = 30
    pre_auth_token_minutes: int = 5

    # Cifra dos segredos TOTP (AES-GCM, chave de 32 bytes em base64)
    totp_encryption_key: str | None = None
    totp_encryption_key_file: str = "/run/secrets/totp_encryption_key"
    totp_issuer: str = "SlotUp"

    # Proteção contra tentativas repetidas (password e código TOTP)
    max_failed_attempts: int = 10
    lock_minutes: int = 15

    # Administrador inicial (opcional; criado no arranque se não existir)
    admin_name: str | None = None
    admin_email: str | None = None
    admin_password: str | None = None

    @property
    def database_url(self) -> URL:
        # URL.create trata de escapar caracteres especiais na password
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

    def totp_key_b64(self) -> str:
        if self.totp_encryption_key:
            return self.totp_encryption_key
        return Path(self.totp_encryption_key_file).read_text().strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
