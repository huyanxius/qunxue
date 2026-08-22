from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


def test_m5_parallel_head_enforces_document_and_handoff_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'm5-identity.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    command.upgrade(alembic_config, "20260820_0005")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        user_id, email, password_hash, created_at, updated_at
                    ) VALUES (
                        'user-1', 'm5-migration@example.com', 'hash',
                        '2026-08-22T07:00:00+00:00',
                        '2026-08-22T07:00:00+00:00'
                    );
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO research_tasks (
                        task_id, user_id, entry_type, status, version,
                        idempotency_key, adopted_theory_count,
                        current_framework_id, created_at, updated_at
                    ) VALUES (
                        'task-1', 'user-1', 'direct_input', 'framework_draft', 4,
                        'task-key', 1, 'document-1',
                        '2026-08-22T07:00:00+00:00',
                        '2026-08-22T07:00:00+00:00'
                    );
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO match_runs (
                        match_run_id, task_id, version, status, snapshot, created_at
                    ) VALUES (
                        'match-1', 'task-1', 1, 'completed', '{}',
                        '2026-08-22T07:00:00+00:00'
                    );
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO theory_decision_sets (
                        decision_set_id, match_run_id, version, snapshot, created_at
                    ) VALUES (
                        'decision-1', 'match-1', 1, '{}',
                        '2026-08-22T07:00:00+00:00'
                    );
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO confirmed_theory_plans (
                        theory_plan_id, task_id, match_run_id, decision_set_id,
                        version, adopted_candidate_ids, confirmed_at
                    ) VALUES (
                        'plan-1', 'task-1', 'match-1', 'decision-1',
                        1, '[]', '2026-08-22T07:00:00+00:00'
                    );
                    """
                )
            )
            for suffix in ("1", "2", "3"):
                connection.execute(
                    text(
                        """
                        INSERT INTO agent_conversations (
                            conversation_id, user_id, title, version,
                            created_at, updated_at
                        ) VALUES (
                            :conversation_id, 'user-1', '研究协作', 1,
                            '2026-08-22T07:00:00+00:00',
                            '2026-08-22T07:00:00+00:00'
                        )
                        """
                    ),
                    {"conversation_id": f"conversation-{suffix}"},
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO agent_runs (
                            run_id, conversation_id, user_id, idempotency_key,
                            status, provider, model, knowledge_release_id,
                            usage, tool_summary, started_at, completed_at
                        ) VALUES (
                            :run_id, :conversation_id, 'user-1', :idempotency_key,
                            'completed', 'test', 'test', 'release-1',
                            '{}', '[]', '2026-08-22T07:00:00+00:00',
                            '2026-08-22T07:01:00+00:00'
                        )
                        """
                    ),
                    {
                        "run_id": f"run-{suffix}",
                        "conversation_id": f"conversation-{suffix}",
                        "idempotency_key": f"run-key-{suffix}",
                    },
                )
        document_payload = {
            "version": 1,
            "task_id": "task-1",
            "theory_plan_id": "plan-1",
            "knowledge_release_id": "release-1",
            "title": "研究框架",
            "sections": "[]",
            "status": "draft",
            "change_summary": "创建",
            "actor": "user",
            "created_at": "2026-08-22T08:00:00+00:00",
        }
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO research_document_versions (
                        document_id, version, task_id, theory_plan_id,
                        knowledge_release_id, revision_id, title, sections,
                        status, change_summary, actor, created_at
                    ) VALUES (
                        :document_id, :version, :task_id, :theory_plan_id,
                        :knowledge_release_id, :revision_id, :title, :sections,
                        :status, :change_summary, :actor, :created_at
                    )
                    """
                ),
                {
                    **document_payload,
                    "document_id": "document-1",
                    "revision_id": "revision-1",
                },
            )
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO research_document_versions (
                        document_id, version, task_id, theory_plan_id,
                        knowledge_release_id, revision_id, title, sections,
                        status, change_summary, actor, created_at
                    ) VALUES (
                        :document_id, :version, :task_id, :theory_plan_id,
                        :knowledge_release_id, :revision_id, :title, :sections,
                        :status, :change_summary, :actor, :created_at
                    )
                    """
                ),
                {
                    **document_payload,
                    "document_id": "document-2",
                    "revision_id": "revision-2",
                    "created_at": "2026-08-22T09:00:00+00:00",
                },
            )

        proposal_payload = {
            "kind": "create",
            "status": "pending",
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "agent_run_id": "run-1",
            "task_id": "task-1",
            "theory_plan_id": "plan-1",
            "knowledge_release_id": "release-1",
            "title": "研究框架",
            "proposed_sections": "[]",
            "rationale": "生成草稿",
            "request_hash": "sha256:first",
            "created_at": "2026-08-22T08:00:00+00:00",
        }
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO research_document_proposals (
                        proposal_id, kind, status, user_id, conversation_id,
                        agent_run_id, task_id, theory_plan_id,
                        knowledge_release_id, title, proposed_sections,
                        rationale, request_hash, created_at
                    ) VALUES (
                        :proposal_id, :kind, :status, :user_id, :conversation_id,
                        :agent_run_id, :task_id, :theory_plan_id,
                        :knowledge_release_id, :title, :proposed_sections,
                        :rationale, :request_hash, :created_at
                    )
                    """
                ),
                {**proposal_payload, "proposal_id": "proposal-1"},
            )
            connection.execute(
                text(
                    """
                    UPDATE research_document_proposals
                    SET status = 'accepted',
                        result_document_id = 'document-2',
                        result_document_version = 1,
                        decision_reason = '历史接受的非当前文档',
                        decided_at = '2026-08-22T08:05:00+00:00'
                    WHERE proposal_id = 'proposal-1'
                    """
                )
            )
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO research_document_proposals (
                        proposal_id, kind, status, user_id, conversation_id,
                        agent_run_id, task_id, theory_plan_id,
                        knowledge_release_id, title, proposed_sections,
                        rationale, request_hash, created_at
                    ) VALUES (
                        :proposal_id, :kind, :status, :user_id, :conversation_id,
                        :agent_run_id, :task_id, :theory_plan_id,
                        :knowledge_release_id, :title, :proposed_sections,
                        :rationale, :request_hash, :created_at
                    )
                    """
                ),
                {
                    **proposal_payload,
                    "proposal_id": "proposal-2",
                    "conversation_id": "conversation-2",
                    "agent_run_id": "run-2",
                    "created_at": "2026-08-22T09:00:00+00:00",
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO research_document_proposals (
                        proposal_id, kind, status, user_id, conversation_id,
                        agent_run_id, task_id, theory_plan_id,
                        knowledge_release_id, title, proposed_sections,
                        rationale, request_hash, result_document_id,
                        result_document_version, decision_reason, created_at, decided_at
                    ) VALUES (
                        'proposal-3', :kind, 'accepted', :user_id, 'conversation-3',
                        'run-3', :task_id, :theory_plan_id,
                        :knowledge_release_id, :title, :proposed_sections,
                        :rationale, 'sha256:canonical-accepted', 'document-1',
                        1, '接受并创建当前文档',
                        '2026-08-22T07:30:00+00:00',
                        '2026-08-22T07:35:00+00:00'
                    )
                    """
                ),
                proposal_payload,
            )
    finally:
        engine.dispose()

    command.upgrade(alembic_config, "20260822_0007_m5")
    engine = create_engine(database_url)
    try:
        assert "research_document_identities" in inspect(engine).get_table_names()
        assert "research_document_handoffs" in inspect(engine).get_table_names()
        with engine.connect() as connection:
            identity = connection.execute(
                text(
                    """
                    SELECT document_id
                    FROM research_document_identities
                    WHERE task_id = 'task-1' AND theory_plan_id = 'plan-1'
                    """
                )
            ).scalar_one()
            handoff = connection.execute(
                text(
                    """
                    SELECT proposal_id
                    FROM research_document_handoffs
                    WHERE user_id = 'user-1'
                      AND task_id = 'task-1'
                      AND theory_plan_id = 'plan-1'
                    """
                )
            ).scalar_one()
            proposals = connection.execute(
                text(
                    """
                    SELECT proposal_id, status, model_provider, model_name
                    FROM research_document_proposals
                    ORDER BY proposal_id
                    """
                )
            ).all()
        assert identity == "document-1"
        assert handoff == "proposal-3"
        assert proposals == [
            ("proposal-1", "accepted", "test", "test"),
            ("proposal-2", "pending", "test", "test"),
            ("proposal-3", "accepted", "test", "test"),
        ]

        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO research_document_identities (
                        task_id, theory_plan_id, document_id
                    ) VALUES ('task-1', 'plan-1', 'document-3')
                    """
                )
            )
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO research_document_handoffs (
                        user_id, task_id, theory_plan_id, proposal_id
                    ) VALUES (
                        'user-1', 'task-1', 'plan-1', 'proposal-3'
                    )
                    """
                )
            )
    finally:
        engine.dispose()

    command.downgrade(alembic_config, "20260820_0005")
    downgraded_engine = create_engine(database_url)
    try:
        assert "research_document_identities" not in inspect(
            downgraded_engine
        ).get_table_names()
        assert "research_document_handoffs" not in inspect(
            downgraded_engine
        ).get_table_names()
    finally:
        downgraded_engine.dispose()
