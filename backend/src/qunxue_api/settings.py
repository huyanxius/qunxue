from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal, cast

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_ROOT = BACKEND_ROOT.parent / "knowledge"
DEFAULT_DATABASE_URL = f"sqlite:///{BACKEND_ROOT / 'var' / 'qunxue.db'}"
DEFAULT_RETRIEVAL_INDEX_PATH = BACKEND_ROOT / "var" / "retrieval.db"
SILICONFLOW_EMBEDDING_MODEL = "Pro/BAAI/bge-m3"
SILICONFLOW_RERANKER_MODEL = "Pro/BAAI/bge-reranker-v2-m3"
DEFAULT_MODEL_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL_NAME = "deepseek-v4-flash"


@dataclass(frozen=True, slots=True)
class RetrievalConfig:
    index_path: Path
    embedding_base_url: str
    embedding_api_key: SecretStr
    embedding_model: str
    embedding_timeout_seconds: float
    embedding_batch_size: int
    reranker_base_url: str
    reranker_api_key: SecretStr
    reranker_model: str
    reranker_timeout_seconds: float
    min_rerank_score: float
    min_lexical_score: float
    recall_limit: int


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
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    account_initial_admin_email: str = ""
    account_initial_admin_password: SecretStr | None = None
    resend_api_key: SecretStr | None = None
    email_from: str = "群学致知 <noreply@qunxue.qiyuankaiwu.com>"
    cors_allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5178",
        "http://localhost:5173",
        "http://localhost:5178",
    )
    model_base_url: str | None = None
    model_api_key: SecretStr | None = None
    model_fallbacks: list[dict[str, str]] = Field(default_factory=list)
    model_name: str | None = None
    model_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] | None
    ) = None
    model_timeout_seconds: float = Field(default=30, gt=0)
    model_extra_headers: dict[str, SecretStr] = Field(default_factory=dict)
    web_search_provider: Literal["bing", "tavily", "brave", "custom"] = "bing"
    web_search_api_key: SecretStr | None = None
    web_search_base_url: str | None = None
    web_search_profile: Literal["generic", "sociology"] = "sociology"
    web_search_allowed_domains: tuple[str, ...] = ()
    web_search_timeout_seconds: float = Field(default=12, gt=0)
    model_sft_resource_header: str = "X-LoRA-ID"
    model_sft_resource_id: SecretStr | None = None
    transcription_base_url: str | None = None
    transcription_api_key: SecretStr | None = None
    transcription_model: str | None = None
    transcription_processing_location: Literal["local", "external"] = "external"
    transcription_timeout_seconds: float = Field(default=180, gt=0)
    embedding_base_url: str | None = None
    embedding_api_key: SecretStr | None = None
    embedding_model: str | None = None
    embedding_timeout_seconds: float = Field(default=15, gt=0)
    reranker_base_url: str | None = None
    reranker_api_key: SecretStr | None = None
    reranker_model: str | None = None
    reranker_timeout_seconds: float = Field(default=15, gt=0)
    retrieval_index_path: Path = DEFAULT_RETRIEVAL_INDEX_PATH
    retrieval_embedding_batch_size: int = Field(default=32, gt=0)
    retrieval_min_rerank_score: float = Field(default=0.01, ge=0, le=1)
    retrieval_min_lexical_score: float = Field(default=0.12, ge=0, le=1)
    retrieval_recall_limit: int = Field(default=30, gt=0)

    model_config = SettingsConfigDict(
        env_prefix="QUNXUE_",
        env_file=BACKEND_ROOT / ".env",
        extra="ignore",
    )

    @property
    def has_model_api_key(self) -> bool:
        """Treat an empty SecretStr like an absent key at runtime boundaries."""
        return self.model_api_key is not None and bool(
            self.model_api_key.get_secret_value().strip()
        )

    @property
    def has_resend_api_key(self) -> bool:
        return self.resend_api_key is not None and bool(
            self.resend_api_key.get_secret_value().strip()
        )

    @property
    def has_transcription_provider(self) -> bool:
        return bool(
            self.transcription_base_url
            and self.transcription_base_url.strip()
            and self.transcription_api_key
            and self.transcription_api_key.get_secret_value().strip()
            and self.transcription_model
            and self.transcription_model.strip()
        )

    def require_retrieval_config(self) -> RetrievalConfig:
        text_fields = {
            "embedding_base_url": self.embedding_base_url,
            "embedding_model": self.embedding_model,
            "reranker_base_url": self.reranker_base_url,
            "reranker_model": self.reranker_model,
        }
        secret_fields = {
            "embedding_api_key": self.embedding_api_key,
            "reranker_api_key": self.reranker_api_key,
        }
        missing = [
            name for name, value in text_fields.items() if value is None or not value.strip()
        ]
        missing.extend(
            name
            for name, value in secret_fields.items()
            if value is None or not value.get_secret_value().strip()
        )
        if missing:
            raise ValueError(
                "retrieval configuration requires non-empty values for: "
                + ", ".join(sorted(missing))
            )
        if self.embedding_model.strip() != SILICONFLOW_EMBEDDING_MODEL:
            raise ValueError("embedding_model must be " + SILICONFLOW_EMBEDDING_MODEL)
        if self.reranker_model.strip() != SILICONFLOW_RERANKER_MODEL:
            raise ValueError("reranker_model must be " + SILICONFLOW_RERANKER_MODEL)
        return RetrievalConfig(
            index_path=self.retrieval_index_path,
            embedding_base_url=cast(str, self.embedding_base_url).strip(),
            embedding_api_key=cast(SecretStr, self.embedding_api_key),
            embedding_model=cast(str, self.embedding_model).strip(),
            embedding_timeout_seconds=self.embedding_timeout_seconds,
            embedding_batch_size=self.retrieval_embedding_batch_size,
            reranker_base_url=cast(str, self.reranker_base_url).strip(),
            reranker_api_key=cast(SecretStr, self.reranker_api_key),
            reranker_model=cast(str, self.reranker_model).strip(),
            reranker_timeout_seconds=self.reranker_timeout_seconds,
            min_rerank_score=self.retrieval_min_rerank_score,
            min_lexical_score=self.retrieval_min_lexical_score,
            recall_limit=self.retrieval_recall_limit,
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

    @field_validator("retrieval_index_path")
    @classmethod
    def resolve_retrieval_index_path(cls, value: Path) -> Path:
        path = value.expanduser()
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        return path.resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
