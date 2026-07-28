from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "群学致知 API"
    contract_version: str = "2026-07-foundation"
    runtime_mode: str = "inline_demo"
    database_url: str = "sqlite:///./var/qunxue.db"

    model_config = SettingsConfigDict(
        env_prefix="QUNXUE_",
        env_file=".env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
