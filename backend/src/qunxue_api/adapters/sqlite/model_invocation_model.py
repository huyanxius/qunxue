from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from qunxue_api.adapters.sqlite.base import Base


class ModelInvocationRow(Base):
    __tablename__ = "model_invocations"

    trace_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    capability_tier: Mapped[str] = mapped_column(String(32), nullable=False)
    demonstration: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scenario: Mapped[str] = mapped_column(String(64), nullable=False)
    input_evidence: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    output: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    knowledge_release_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    degraded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    degradation_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
