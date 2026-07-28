"""SQLite adapter registry used by migrations and the composition root."""

from qunxue_api.adapters.sqlite.base import Base
from qunxue_api.adapters.sqlite.research_intake_model import ResearchTaskRow

__all__ = ["Base", "ResearchTaskRow"]
