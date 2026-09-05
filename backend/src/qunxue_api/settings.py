from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
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


def _normalize_model_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("model base URL must be an HTTP(S) URL without credentials")
    return value.rstrip("/")


def _normalize_model_name(value: str) -> str:
    if not value.strip():
        raise ValueError("model name must not be empty")
    return value.strip()


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


@dataclass(frozen=True, slots=True)
class ResolvedModelEndpointSettings:
    """Validated model endpoint configuration without adapter dependencies."""

    endpoint_id: str
    base_url: str
    model: str
    api_key: SecretStr | None = field(repr=False)
    timeout_seconds: float


class ModelFallbackSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    base_url: str
    api_key: SecretStr
    model: str | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return _normalize_model_base_url(value)

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_model_name(value)


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
    release_revision: str = Field(
        default="unreleased",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    runtime_mode: Literal["mock", "base", "sft"] = "mock"
    database_url: str = DEFAULT_DATABASE_URL
    memory_learning_enabled: bool = True
    memory_learning_idle_seconds: int = Field(default=600, ge=60)
    memory_learning_daily_calls: int = Field(default=8, ge=0, le=32)
    memory_learning_daily_tokens: int = Field(default=64000, ge=0, le=256000)
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
    model_fallbacks: list[ModelFallbackSettings] = Field(default_factory=list)
    model_name: str | None = None
    model_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] | None
    ) = None
    model_timeout_seconds: float = Field(default=30, gt=0)
    model_probe_interval_seconds: float = Field(default=300, gt=0)
    model_extra_headers: dict[str, SecretStr] = Field(default_factory=dict)
    web_search_provider: Literal["tavily", "custom"] = "tavily"
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
        hide_input_in_errors=True,
    )

    @field_validator("model_base_url")
    @classmethod
    def validate_model_base_url(cls, value: str | None) -> str | None:
        return _normalize_model_base_url(value) if value is not None else None

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, value: str | None) -> str | None:
        return _normalize_model_name(value) if value is not None else None

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

    def resolved_model_endpoints(self) -> tuple[ResolvedModelEndpointSettings, ...]:
        primary_base_url = self.model_base_url or (
            DEFAULT_MODEL_BASE_URL if self.has_model_api_key else None
        )
        primary_model = self.model_name or (
            DEFAULT_MODEL_NAME if self.has_model_api_key else None
        )
        if primary_base_url is None and primary_model is None and not self.model_fallbacks:
            return ()
        if primary_base_url is None or primary_model is None:
            raise ValueError("model_base_url and model_name must be configured together")
        endpoints = [
            ResolvedModelEndpointSettings(
                endpoint_id="primary",
                base_url=primary_base_url,
                api_key=self.model_api_key,
                model=primary_model,
                timeout_seconds=self.model_timeout_seconds,
            )
        ]
        endpoints.extend(
            ResolvedModelEndpointSettings(
                endpoint_id=f"fallback-{index}",
                base_url=fallback.base_url,
                api_key=fallback.api_key,
                model=fallback.model or primary_model,
                timeout_seconds=self.model_timeout_seconds,
            )
            for index, fallback in enumerate(self.model_fallbacks, start=1)
        )
        return tuple(endpoints)

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
