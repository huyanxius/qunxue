from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_existing_users_remain_members_with_secondary_model_use_denied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> None:
    database_path = tmp_path / "upgrade-account.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    command.upgrade(alembic_config, "20260820_0005")
    user_id = str(uuid4())
    task_id = str(uuid4())
    conversation_id = str(uuid4())
    run_id = str(uuid4())
    now = datetime(2026, 8, 22, tzinfo=UTC)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        user_id, email, password_hash, display_name, created_at, updated_at
                    ) VALUES (
                        :user_id, :email, :password_hash, NULL, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "user_id": user_id,
                    "email": "legacy@example.com",
                    "password_hash": "legacy-hash",
                    "created_at": now,
                    "updated_at": now,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO research_tasks (
                        task_id, user_id, entry_type, status, version,
                        idempotency_key, adopted_theory_count,
                        created_at, updated_at
                    ) VALUES (
                        :task_id, :user_id, 'direct_input', 'draft', 1,
                        'legacy-task', 0, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "task_id": task_id,
                    "user_id": user_id,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO agent_conversations (
                        conversation_id, user_id, title, version,
                        created_at, updated_at
                    ) VALUES (
                        :conversation_id, :user_id, '旧研究对话', 1,
                        :created_at, :updated_at
                    )
                    """
                ),
                {
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO agent_runs (
                        run_id, conversation_id, user_id, idempotency_key,
                        status, provider, model, knowledge_release_id,
                        usage, tool_summary, started_at, completed_at
                    ) VALUES (
                        :run_id, :conversation_id, :user_id, 'legacy-run',
                        'completed', 'test', 'test', 'release-legacy',
                        '{}', '[]', :created_at, :updated_at
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        command.upgrade(alembic_config, "head")

        with engine.connect() as connection:
            user = connection.execute(
                text("SELECT role, status, version FROM users WHERE user_id = :user_id"),
                {"user_id": user_id},
            ).one()
            preference = connection.execute(
                text(
                    """
                    SELECT model_improvement_allowed, consent_policy_version, version
                    FROM user_preferences
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            ).one()
            bootstrap = connection.execute(
                text(
                    "SELECT initial_admin_provisioned "
                    "FROM account_system_state WHERE singleton_id = 1"
                )
            ).one()
            preserved = connection.execute(
                text(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM research_tasks WHERE task_id = :task_id),
                        (SELECT COUNT(*) FROM agent_conversations
                         WHERE conversation_id = :conversation_id),
                        (SELECT COUNT(*) FROM agent_runs WHERE run_id = :run_id)
                    """
                ),
                {
                    "task_id": task_id,
                    "conversation_id": conversation_id,
                    "run_id": run_id,
                },
            ).one()

        assert tuple(user) == ("member", "active", 1)
        assert tuple(preference) == (0, "2026-08-secondary-use-v1", 1)
        assert bootstrap.initial_admin_provisioned == 0
        assert tuple(preserved) == (1, 1, 1)
        assert {
            "account_audit_events",
            "account_mutation_requests",
            "account_password_resets",
            "personal_data_exports",
            "user_preferences",
        } <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
