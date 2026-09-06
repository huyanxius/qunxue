"""End-to-end test server: deterministic Mock runtime, no email gate, throwaway DB.

Production never imports this. `qunxue_api.main` keeps the real defaults
(`require_email_verification=True`); this entrypoint exists only so a browser
test can register a user and drive the research flow without a mail provider.

Each start gets its own fresh SQLite file under ``backend/var/e2e/`` so parallel
or leaked runs never block one another. Stale files are swept best-effort.
Override the location with ``QUNXUE_DATABASE_URL`` and the bind address with
``QUNXUE_E2E_HOST`` / ``QUNXUE_E2E_PORT``.
"""

import contextlib
import os
import time
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config

from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.bootstrap import create_app
from qunxue_api.modules.knowledge_catalog import KnowledgeUsePurpose
from qunxue_api.settings import BACKEND_ROOT, Settings

HOST = os.environ.get("QUNXUE_E2E_HOST", "127.0.0.1")
PORT = int(os.environ.get("QUNXUE_E2E_PORT", "8000"))
E2E_DIR = BACKEND_ROOT / "var" / "e2e"


def _sweep(directory: Path) -> None:
    for stale in directory.glob("run-*.db*"):
        # A leaked server may still hold one; skip it rather than fail the run.
        with contextlib.suppress(OSError):
            stale.unlink()


def _database_url() -> str:
    override = os.environ.get("QUNXUE_DATABASE_URL", "").strip()
    if override:
        return override
    E2E_DIR.mkdir(parents=True, exist_ok=True)
    _sweep(E2E_DIR)
    path = E2E_DIR / f"run-{os.getpid()}-{int(time.time())}.db"
    return f"sqlite:///{path.as_posix()}"


def main() -> None:
    database_url = _database_url()
    os.environ["QUNXUE_DATABASE_URL"] = database_url

    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")

    settings = Settings(
        _env_file=None,
        database_url=database_url,
        runtime_mode="mock",
        model_base_url=None,
        model_api_key=None,
        model_name=None,
        model_extra_headers={},
        model_sft_resource_id=None,
    )
    app = create_app(
        settings=settings,
        database=Database(settings.database_url),
        require_email_verification=False,
    )
    # First access builds the deterministic BROWSE release from knowledge/ markdown.
    # Do it before serving so the readiness probe on /api/health is not the caller.
    app.state.knowledge_catalog.current_release(purpose=KnowledgeUsePurpose.BROWSE)

    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
