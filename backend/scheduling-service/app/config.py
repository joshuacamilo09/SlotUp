from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    service_name: str = "scheduling-service"


@lru_cache
def get_settings() -> Settings:
    return Settings()
