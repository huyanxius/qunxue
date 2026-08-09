from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_ROOT = BACKEND_ROOT.parent / "knowledge"
DEFAULT_DATABASE_URL = f"sqlite:///{BACKEND_ROOT / 'var' / 'qunxue.db'}"


def is_sqlite_memory_url(database_url: str) -> bool:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return False
    return (
        url.database
        in {
            None,
            "",
            ":memory:",
            "file::memory:",
        }
        or url.query.get("mode") == "memory"
    )


class Settings(BaseSettings):
    app_name: str = "群学致知 API"
    contract_version: str = "2026-07-foundation"
    runtime_mode: Literal["mock", "base", "sft"] = "mock"
    database_url: str = DEFAULT_DATABASE_URL
    session_cookie_name: str = "qunxue_session"
    session_ttl_seconds: int = 60 * 60 * 24 * 7
    session_cookie_secure: bool = False
    model_base_url: str | None = None
    model_api_key: SecretStr | None = None
    model_name: str | None = None
    model_timeout_seconds: float = Field(default=30, gt=0)
    model_extra_headers: dict[str, SecretStr] = Field(default_factory=dict)
    model_sft_resource_header: str = "X-LoRA-ID"
    model_sft_resource_id: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_prefix="QUNXUE_",
        env_file=BACKEND_ROOT / ".env",
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def resolve_sqlite_database_path(cls, database_url: str) -> str:
        url = make_url(database_url)
        if (
            url.get_backend_name() != "sqlite"
            or is_sqlite_memory_url(database_url)
            or url.database is None
        ):
            return database_url

        database_path = Path(url.database).expanduser()
        if not database_path.is_absolute():
            database_path = BACKEND_ROOT / database_path
        return url.set(database=str(database_path.resolve())).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
