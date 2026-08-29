from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from uuid import UUID

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.research_material_model import (
    ResearchMaterialBlobRow,
    ResearchMaterialBlockRow,
    ResearchMaterialParseVersionRow,
    ResearchMaterialRow,
)
from qunxue_api.adapters.sqlite.research_material_repository import (
    SqliteResearchMaterialRepository,
)
from qunxue_api.modules.research_materials import (
    MaterialBlock,
    MaterialIdempotencyConflict,
    MaterialKind,
    MaterialLocator,
    MaterialParseVersion,
    MaterialStatus,
    MaterialVersionConflict,
)


def _create_tables(engine) -> None:
    for table in (
        ResearchMaterialRow.__table__,
        ResearchMaterialBlobRow.__table__,
        ResearchMaterialParseVersionRow.__table__,
        ResearchMaterialBlockRow.__table__,
    ):
        table.create(engine, checkfirst=True)


def _upload(repo: SqliteResearchMaterialRepository, *, key: str = "upload-1"):
    return repo.create(
        user_id=UUID(int=1),
        task_id=UUID(int=2),
        idempotency_key=key,
        filename="访谈.txt",
        media_type="text/plain",
        content="第一段\n\n第二段".encode(),
        material_kind=MaterialKind.INTERVIEW_TRANSCRIPT,
        display_name="访谈材料",
        processing_policy_version="2026-08-29",
        now=datetime(2026, 8, 29, 12, tzinfo=UTC),
    )


def _parse(material_id: UUID, *, version: int = 1, parse_id: UUID | None = None):
    parse_id = parse_id or UUID(int=3)
    block = MaterialBlock.create(
        parse_id=parse_id,
        material_id=material_id,
        ordinal=0,
        kind="paragraph",
        text="第一段",
        locator=MaterialLocator(paragraph=1, char_start=0, char_end=3),
    )
    return MaterialParseVersion.create(
        parse_id=parse_id,
        material_id=material_id,
        version=version,
        parser_name="test-parser",
        parser_version="1.0",
        schema_version="1",
        full_text="第一段\n\n第二段",
        structured_document={"blocks": 1},
        blocks=(block,),
        content_hash="c" * 64,
        now=datetime(2026, 8, 29, 12, 1, tzinfo=UTC),
    )


def test_repository_round_trips_blob_parse_and_stable_segment() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as session:
        repo = SqliteResearchMaterialRepository(session)
        material = _upload(repo)
        persisted = repo.save_parse(_parse(material.material_id))
        session.commit()

        restored = repo.get(
            material.material_id,
            user_id=UUID(int=1),
            task_id=UUID(int=2),
        )
        blob = repo.get_original(
            material.material_id,
            user_id=UUID(int=1),
            task_id=UUID(int=2),
        )
        segment = repo.get_segment(
            material.material_id,
            persisted.parse_id,
            persisted.blocks[0].block_id,
            user_id=UUID(int=1),
            task_id=UUID(int=2),
        )

    assert restored is not None
    assert restored.status is MaterialStatus.READY
    assert restored.current_parse_version == 1
    assert blob == "第一段\n\n第二段".encode()
    assert segment is not None
    assert segment.locator.page is None
    assert segment.locator.paragraph == 1
    engine.dispose()


def test_repository_upload_is_idempotent_and_reads_are_strictly_owned() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as session:
        repo = SqliteResearchMaterialRepository(session)
        first = _upload(repo)
        replay = _upload(repo)
        assert replay.material_id == first.material_id
        assert repo.get(first.material_id, user_id=UUID(int=9), task_id=UUID(int=2)) is None
        assert repo.get(first.material_id, user_id=UUID(int=1), task_id=UUID(int=9)) is None
    engine.dispose()


def test_idempotency_key_rejects_changed_material_metadata() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as session:
        repo = SqliteResearchMaterialRepository(session)
        _upload(repo)
        try:
            repo.create(
                user_id=UUID(int=1),
                task_id=UUID(int=2),
                idempotency_key="upload-1",
                filename="访谈.txt",
                media_type="text/plain",
                content="第一段\n\n第二段".encode(),
                material_kind=MaterialKind.FIELD_NOTE,
                display_name="田野笔记",
                processing_policy_version="2026-08-29",
                now=datetime(2026, 8, 29, 12, tzinfo=UTC),
            )
        except MaterialIdempotencyConflict:
            pass
        else:
            raise AssertionError("an idempotency replay must preserve request metadata")
    engine.dispose()


def test_concurrent_upload_idempotency_replays_one_material(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'materials.db'}",
        connect_args={"timeout": 5},
    )
    _create_tables(engine)
    barrier = Barrier(2)

    def upload() -> UUID:
        with Session(engine) as session:
            barrier.wait()
            material = _upload(SqliteResearchMaterialRepository(session))
            session.commit()
            return material.material_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        material_ids = list(executor.map(lambda _index: upload(), range(2)))

    assert len(set(material_ids)) == 1
    engine.dispose()


def test_repository_reparse_appends_version_and_keeps_old_parse_traceable() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as session:
        repo = SqliteResearchMaterialRepository(session)
        material = _upload(repo)
        first = repo.save_parse(_parse(material.material_id))
        second = repo.save_parse(
            _parse(material.material_id, version=2, parse_id=UUID(int=4))
        )
        old = repo.get_parse(
            material.material_id,
            first.parse_id,
            user_id=UUID(int=1),
            task_id=UUID(int=2),
        )
        current = repo.get(material.material_id, user_id=UUID(int=1), task_id=UUID(int=2))
        session.commit()

    assert old is not None
    assert old.version == 1
    assert current is not None
    assert current.current_parse_id == second.parse_id
    assert current.current_parse_version == 2
    engine.dispose()


def test_repository_delete_clears_content_and_leaves_tombstone() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as session:
        repo = SqliteResearchMaterialRepository(session)
        material = _upload(repo)
        repo.save_parse(_parse(material.material_id))
        deleted = repo.delete(
            material.material_id,
            user_id=UUID(int=1),
            task_id=UUID(int=2),
            idempotency_key="delete-1",
            now=datetime(2026, 8, 29, 12, 6, tzinfo=UTC),
        )
        assert deleted is not None
        assert deleted.status is MaterialStatus.DELETED
        assert (
            repo.get_original(
                material.material_id,
                user_id=UUID(int=1),
                task_id=UUID(int=2),
            )
            is None
        )
        assert (
            repo.get_parse(
                material.material_id,
                UUID(int=3),
                user_id=UUID(int=1),
                task_id=UUID(int=2),
            )
            is None
        )
        assert (
            repo.get_segment(
                material.material_id,
                UUID(int=3),
                "missing",
                user_id=UUID(int=1),
                task_id=UUID(int=2),
            )
            is None
        )
        session.commit()

    with Session(engine) as session:
        assert session.scalar(select(ResearchMaterialBlobRow)) is None
        assert session.scalar(select(ResearchMaterialParseVersionRow)) is None
        assert session.scalar(select(ResearchMaterialBlockRow)) is None
        tombstone = session.scalar(select(ResearchMaterialRow))
        assert tombstone is not None
        assert tombstone.status == "deleted"
        assert tombstone.deleted_at is not None
    engine.dispose()


def test_failed_parse_attempt_is_traceable_and_next_success_becomes_current() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as session:
        repo = SqliteResearchMaterialRepository(session)
        material = _upload(repo)
        failed = MaterialParseVersion.failed(
            parse_id=UUID(int=5),
            material_id=material.material_id,
            version=1,
            parser_name="test-parser",
            parser_version="1.0",
            schema_version="1",
            error_code="no_extractable_text",
            now=datetime(2026, 8, 29, 12, 1, tzinfo=UTC),
        )
        repo.save_parse(failed)
        retried = repo.save_parse(
            _parse(material.material_id, version=2, parse_id=UUID(int=6))
        )
        current = repo.get(material.material_id, user_id=UUID(int=1), task_id=UUID(int=2))
        history = repo.list_parses(
            material.material_id,
            user_id=UUID(int=1),
            task_id=UUID(int=2),
        )
        session.commit()

    assert retried.version == 2
    assert current is not None
    assert current.status is MaterialStatus.READY
    assert current.current_parse_version == 2
    assert [item.version for item in history] == [2, 1]
    assert history[-1].status is MaterialStatus.FAILED
    engine.dispose()


def test_reparse_compare_and_set_rejects_a_stale_current_version() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as session:
        repo = SqliteResearchMaterialRepository(session)
        material = _upload(repo)
        repo.save_parse(_parse(material.material_id))
        try:
            repo.begin_reparse(
                material.material_id,
                user_id=UUID(int=1),
                task_id=UUID(int=2),
                parse_id=UUID(int=7),
                now=datetime(2026, 8, 29, 12, 2, tzinfo=UTC),
                expected_current_version=0,
            )
        except MaterialVersionConflict:
            pass
        else:
            raise AssertionError("a stale reparse must fail its CAS check")
    engine.dispose()


def test_reparse_compare_and_set_allows_only_one_active_attempt() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    with Session(engine) as session:
        repo = SqliteResearchMaterialRepository(session)
        material = _upload(repo)
        repo.save_parse(_parse(material.material_id))
        repo.begin_reparse(
            material.material_id,
            user_id=UUID(int=1),
            task_id=UUID(int=2),
            parse_id=UUID(int=8),
            now=datetime(2026, 8, 29, 12, 2, tzinfo=UTC),
            expected_current_version=1,
        )
        try:
            repo.begin_reparse(
                material.material_id,
                user_id=UUID(int=1),
                task_id=UUID(int=2),
                parse_id=UUID(int=9),
                now=datetime(2026, 8, 29, 12, 3, tzinfo=UTC),
                expected_current_version=1,
            )
        except MaterialVersionConflict:
            pass
        else:
            raise AssertionError("only one parse attempt may own the material")
    engine.dispose()


def test_deleting_research_task_cascades_all_material_content() -> None:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE users (user_id VARCHAR(36) PRIMARY KEY)"
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE research_tasks (
                task_id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(36) REFERENCES users(user_id) ON DELETE CASCADE
            )
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO users (user_id) VALUES (?)",
            (str(UUID(int=1)),),
        )
        connection.exec_driver_sql(
            "INSERT INTO research_tasks (task_id, user_id) VALUES (?, ?)",
            (str(UUID(int=2)), str(UUID(int=1))),
        )
    _create_tables(engine)
    with Session(engine) as session:
        repo = SqliteResearchMaterialRepository(session)
        material = _upload(repo)
        repo.save_parse(_parse(material.material_id))
        session.commit()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "DELETE FROM research_tasks WHERE task_id = ?",
            (str(UUID(int=2)),),
        )
    with Session(engine) as session:
        assert session.scalar(select(ResearchMaterialRow)) is None
        assert session.scalar(select(ResearchMaterialBlobRow)) is None
        assert session.scalar(select(ResearchMaterialParseVersionRow)) is None
        assert session.scalar(select(ResearchMaterialBlockRow)) is None
    engine.dispose()
