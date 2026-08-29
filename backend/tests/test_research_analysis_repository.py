from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Column, MetaData, String, Table, create_engine
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.base import Base
from qunxue_api.adapters.sqlite.identity_model import UserRow
from qunxue_api.adapters.sqlite.research_analysis_model import (
    ResearchAnalysisWriteRequestRow,
    ResearchAnnotationRow,
    ResearchCodeRow,
    ResearchComparisonRow,
    ResearchMemoRow,
)
from qunxue_api.adapters.sqlite.research_analysis_repository import (
    SqliteResearchAnalysisRepository,
)
from qunxue_api.adapters.sqlite.research_intake_model import ResearchTaskRow
from qunxue_api.adapters.sqlite.research_material_model import ResearchMaterialRow
from qunxue_api.modules.research_analysis import (
    AnalysisAnnotation,
    AnalysisAnnotationKind,
    AnalysisCode,
    AnalysisMemo,
    AnalysisMemoKind,
    AnalysisWriteRequest,
    CaseComparison,
    ComparisonFinding,
    ComparisonFindingKind,
    NextResearchStep,
    ResearchAnalysisIdempotencyConflict,
)
from qunxue_api.modules.research_materials import MaterialLocator
from qunxue_api.settings import Settings

_OWNER = UUID(int=1)
_TASK = UUID(int=2)
_MATERIAL = UUID(int=3)
_PARSE = UUID(int=4)
_ANNOTATION = UUID(int=11)
_CODE = UUID(int=21)
_CREATED_AT = datetime(2026, 8, 30, 9, tzinfo=UTC)
_DECIDED_AT = datetime(2026, 8, 30, 10, tzinfo=UTC)
_QUOTE = "有时候不是不想参加，而是不知道自己能不能留下来。"
_SEGMENT_TEXT = f"受访者停顿后说：“{_QUOTE}”随后转向了社区活动的话题。"
_QUOTE_START = 9
_QUOTE_END = _QUOTE_START + len(_QUOTE)
_ANALYSIS_MODELS = (
    ResearchAnalysisWriteRequestRow,
    ResearchAnnotationRow,
    ResearchCodeRow,
    ResearchMemoRow,
    ResearchComparisonRow,
)


def _create_tables(engine) -> None:
    # Register and create only the three FK targets plus this repository's rows.
    for model in (UserRow, ResearchTaskRow, ResearchMaterialRow, *_ANALYSIS_MODELS):
        model.__table__.create(engine, checkfirst=True)


def _annotation(
    *,
    annotation_id: UUID = _ANNOTATION,
    user_id: UUID = _OWNER,
    task_id: UUID = _TASK,
) -> AnalysisAnnotation:
    return AnalysisAnnotation.create(
        annotation_id=annotation_id,
        user_id=user_id,
        task_id=task_id,
        material_id=_MATERIAL,
        parse_id=_PARSE,
        segment_id="segment-0007",
        segment_content_hash=sha256(_SEGMENT_TEXT.encode()).hexdigest(),
        quote=_QUOTE,
        quote_start=_QUOTE_START,
        quote_end=_QUOTE_END,
        locator=MaterialLocator(
            page=7,
            section_path=("访谈二", "居留不确定性"),
            paragraph=12,
            char_start=4,
            char_end=27,
            block_index=31,
        ),
        annotation_kind=AnalysisAnnotationKind.RESEARCHER_REFLECTION,
        case_label="社区甲",
        observed_at="2026-07",
        note="受访者将参与状态与居留时间联系起来。",
        reflection="我可能过早地把这句话解释成归属感不足。",
        now=_CREATED_AT,
    )


def _code(
    annotation: AnalysisAnnotation,
    *,
    code_id: UUID = _CODE,
) -> AnalysisCode:
    return AnalysisCode.candidate(
        code_id=code_id,
        user_id=annotation.user_id,
        task_id=annotation.task_id,
        label="暂时性预期",
        definition="行动者因预期无法长期停留而降低当下参与。",
        annotation_ids=(annotation.annotation_id,),
        rationale="原文直接连接参与与能否留下。",
        now=_CREATED_AT,
    )


def _memo(annotation: AnalysisAnnotation, code: AnalysisCode) -> AnalysisMemo:
    return AnalysisMemo.create_candidate(
        memo_id=UUID(int=31),
        user_id=annotation.user_id,
        task_id=annotation.task_id,
        title="暂时性如何削弱参与",
        content="需要区分实际流动与对流动的预期。",
        memo_kind=AnalysisMemoKind.ANALYTIC,
        annotation_ids=(annotation.annotation_id,),
        code_ids=(code.code_id,),
        now=_CREATED_AT,
    )


def _comparison(annotation: AnalysisAnnotation) -> CaseComparison:
    return CaseComparison.create(
        comparison_id=UUID(int=41),
        user_id=annotation.user_id,
        task_id=annotation.task_id,
        title="社区甲与社区乙的参与差异",
        question="居留预期如何改变社区参与？",
        case_labels=("社区甲", "社区乙"),
        time_labels=("2025", "2026"),
        findings=(
            ComparisonFinding(
                kind=ComparisonFindingKind.SUPPORT,
                statement="社区甲中，短期留居预期与低参与并存。",
                annotation_ids=(annotation.annotation_id,),
            ),
            ComparisonFinding(
                kind=ComparisonFindingKind.COUNTEREXAMPLE,
                statement="社区乙中的短期居住者仍主动组织互助。",
                annotation_ids=(),
            ),
            ComparisonFinding(
                kind=ComparisonFindingKind.CONTRADICT,
                statement="同一受访者的叙述与后续观察不一致。",
                annotation_ids=(annotation.annotation_id,),
            ),
        ),
        competing_explanations=("组织者动员能力差异",),
        evidence_gaps=("缺少社区乙组织者的访谈",),
        next_steps=(
            NextResearchStep(
                kind="interview",
                action="访谈社区乙的组织者，追问其动员策略。",
                priority="high",
            ),
            NextResearchStep(
                kind="observation",
                action="记录两个社区未来三次活动的实际到场情况。",
                priority="medium",
            ),
        ),
        theory_implication="暂时性预期只在缺少稳定动员时削弱参与。",
        now=_CREATED_AT,
    )


def test_repository_round_trips_source_anchor_and_keeps_reflection_separate() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    annotation = _annotation()

    with Session(engine) as session:
        SqliteResearchAnalysisRepository(session).add_annotation(annotation)
        session.commit()

    with Session(engine) as session:
        repository = SqliteResearchAnalysisRepository(session)
        restored = repository.list_annotations(
            user_id=_OWNER,
            task_id=_TASK,
        )
        restored_by_id = repository.get_annotation(
            annotation.annotation_id,
            user_id=_OWNER,
            task_id=_TASK,
        )

    assert restored == (annotation,)
    assert restored[0].note == "受访者将参与状态与居留时间联系起来。"
    assert restored[0].reflection == "我可能过早地把这句话解释成归属感不足。"
    assert restored[0].segment_content_hash == sha256(_SEGMENT_TEXT.encode()).hexdigest()
    assert (restored[0].quote_start, restored[0].quote_end) == (
        _QUOTE_START,
        _QUOTE_END,
    )
    assert restored[0].quote_hash == annotation.quote_hash
    assert restored[0].locator == annotation.locator
    assert restored_by_id == annotation
    engine.dispose()


def test_repository_persists_write_idempotency_and_rejects_changed_payload() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    request = AnalysisWriteRequest.create(
        user_id=_OWNER,
        task_id=_TASK,
        namespace="api",
        idempotency_key="analysis-request-1",
        operation="create_annotation",
        request_hash="a" * 64,
        result_kind="annotation",
        result_id=UUID(int=91),
        now=_CREATED_AT,
    )

    with Session(engine) as session:
        repository = SqliteResearchAnalysisRepository(session)
        assert repository.reserve_write(request) == request
        session.commit()

    replay_candidate = replace(request, result_id=UUID(int=92))
    with Session(engine) as session:
        repository = SqliteResearchAnalysisRepository(session)
        assert repository.reserve_write(replay_candidate) == request
        with pytest.raises(ResearchAnalysisIdempotencyConflict):
            repository.reserve_write(
                replace(
                    replay_candidate,
                    operation="create_user_code",
                    request_hash="b" * 64,
                )
            )
    engine.dispose()


def test_repository_round_trips_agent_candidate_provenance() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    annotation = _annotation()
    code = AnalysisCode.candidate(
        code_id=UUID(int=93),
        user_id=_OWNER,
        task_id=_TASK,
        label="暂时性预期",
        definition="行动者因预期无法长期停留而降低参与。",
        annotation_ids=(annotation.annotation_id,),
        rationale="原文直接连接参与与能否留下。",
        conversation_id=UUID(int=94),
        agent_run_id=UUID(int=95),
        agent_turn_id=UUID(int=96),
        tool_call_id="call-code-1",
        now=_CREATED_AT,
    )
    memo = AnalysisMemo.create_candidate(
        memo_id=UUID(int=97),
        user_id=_OWNER,
        task_id=_TASK,
        title="暂时性如何削弱参与",
        content="需要区分实际流动与对流动的预期。",
        memo_kind=AnalysisMemoKind.ANALYTIC,
        annotation_ids=(annotation.annotation_id,),
        code_ids=(code.code_id,),
        conversation_id=UUID(int=94),
        agent_run_id=UUID(int=95),
        agent_turn_id=UUID(int=96),
        tool_call_id="call-memo-1",
        now=_CREATED_AT,
    )
    comparison = replace(
        _comparison(annotation),
        conversation_id=UUID(int=94),
        agent_run_id=UUID(int=95),
        agent_turn_id=UUID(int=96),
        tool_call_id="call-comparison-1",
    )

    with Session(engine) as session:
        repository = SqliteResearchAnalysisRepository(session)
        repository.add_code(code)
        repository.add_memo(memo)
        repository.add_comparison(comparison)
        session.commit()

    with Session(engine) as session:
        repository = SqliteResearchAnalysisRepository(session)
        assert repository.get_code(code.code_id, user_id=_OWNER, task_id=_TASK) == code
        assert repository.get_memo(memo.memo_id, user_id=_OWNER, task_id=_TASK) == memo
        assert (
            repository.get_comparison(
                comparison.comparison_id,
                user_id=_OWNER,
                task_id=_TASK,
            )
            == comparison
        )
    engine.dispose()


def test_repository_scopes_reads_and_record_identity_to_owner_and_task() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    annotation = _annotation()
    code = _code(annotation)
    memo = _memo(annotation, code)
    comparison = _comparison(annotation)

    with Session(engine) as session:
        repository = SqliteResearchAnalysisRepository(session)
        repository.add_annotation(annotation)
        repository.add_code(code)
        repository.add_memo(memo)
        repository.add_comparison(comparison)
        session.commit()

    with Session(engine) as session:
        repository = SqliteResearchAnalysisRepository(session)
        for wrong_user, wrong_task in ((UUID(int=99), _TASK), (_OWNER, UUID(int=99))):
            assert repository.list_annotations(user_id=wrong_user, task_id=wrong_task) == ()
            assert repository.list_codes(user_id=wrong_user, task_id=wrong_task) == ()
            assert repository.list_memos(user_id=wrong_user, task_id=wrong_task) == ()
            assert repository.list_comparisons(user_id=wrong_user, task_id=wrong_task) == ()
            assert repository.get_code(code.code_id, user_id=wrong_user, task_id=wrong_task) is None
            assert repository.get_memo(memo.memo_id, user_id=wrong_user, task_id=wrong_task) is None
            assert (
                repository.get_comparison(
                    comparison.comparison_id,
                    user_id=wrong_user,
                    task_id=wrong_task,
                )
                is None
            )

    counterfeit = replace(annotation, user_id=UUID(int=99), note="伪造的其他用户记录")
    with Session(engine) as session, pytest.raises(ValueError, match="already belongs"):
        SqliteResearchAnalysisRepository(session).add_annotation(counterfeit)

    with Session(engine) as session:
        restored = SqliteResearchAnalysisRepository(session).list_annotations(
            user_id=_OWNER,
            task_id=_TASK,
        )
    assert restored == (annotation,)
    engine.dispose()


def test_repository_persists_candidate_confirmed_and_rejected_statuses() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    annotation = _annotation()
    code = _code(annotation)
    memo = _memo(annotation, code)
    comparison = _comparison(annotation)

    with Session(engine) as session:
        repository = SqliteResearchAnalysisRepository(session)
        repository.add_annotation(annotation)
        repository.add_code(code)
        repository.add_memo(memo)
        repository.add_comparison(comparison)
        session.commit()

    with Session(engine) as session:
        repository = SqliteResearchAnalysisRepository(session)
        assert repository.get_code(code.code_id, user_id=_OWNER, task_id=_TASK) == code
        assert repository.get_memo(memo.memo_id, user_id=_OWNER, task_id=_TASK) == memo
        assert (
            repository.get_comparison(
                comparison.comparison_id,
                user_id=_OWNER,
                task_id=_TASK,
            )
            == comparison
        )
        assert code.version == memo.version == comparison.version == 1

    confirmed_code = code.confirm(
        user_confirmed=True,
        expected_version=1,
        reason="研究者确认编码",
        now=_DECIDED_AT,
    )
    rejected_memo = memo.reject(
        user_confirmed=True,
        expected_version=1,
        reason="证据不足，暂不纳入分析。",
        now=_DECIDED_AT,
    )
    confirmed_comparison = comparison.confirm(
        user_confirmed=True,
        expected_version=1,
        reason="研究者确认比较",
        now=_DECIDED_AT,
    )
    with Session(engine) as session:
        repository = SqliteResearchAnalysisRepository(session)
        repository.add_code(confirmed_code)
        repository.add_memo(rejected_memo)
        repository.add_comparison(confirmed_comparison)
        session.commit()

    with Session(engine) as session:
        repository = SqliteResearchAnalysisRepository(session)
        assert repository.get_code(code.code_id, user_id=_OWNER, task_id=_TASK) == confirmed_code
        assert repository.get_memo(memo.memo_id, user_id=_OWNER, task_id=_TASK) == rejected_memo
        assert (
            repository.get_comparison(
                comparison.comparison_id,
                user_id=_OWNER,
                task_id=_TASK,
            )
            == confirmed_comparison
        )
        assert confirmed_code.version == rejected_memo.version == 2
        assert confirmed_comparison.version == 2
    engine.dispose()


def test_repository_keeps_the_first_terminal_decision_when_stale_writes_arrive() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    annotation = _annotation()
    code = _code(annotation)
    memo = _memo(annotation, code)
    comparison = _comparison(annotation)

    with Session(engine) as session:
        repository = SqliteResearchAnalysisRepository(session)
        repository.add_code(code)
        repository.add_memo(memo)
        repository.add_comparison(comparison)
        session.commit()

    first_code_decision = code.confirm(
        user_confirmed=True,
        expected_version=1,
        reason="研究者确认编码",
        now=_DECIDED_AT,
    )
    first_memo_decision = memo.reject(
        user_confirmed=True,
        expected_version=1,
        reason="用户判断该备忘与当前问题无关。",
        now=_DECIDED_AT,
    )
    first_comparison_decision = comparison.confirm(
        user_confirmed=True,
        expected_version=1,
        reason="研究者确认比较",
        now=_DECIDED_AT,
    )
    with Session(engine) as session:
        repository = SqliteResearchAnalysisRepository(session)
        assert repository.add_code(first_code_decision) == first_code_decision
        assert repository.add_memo(first_memo_decision) == first_memo_decision
        assert repository.add_comparison(first_comparison_decision) == first_comparison_decision
        session.commit()

    stale_code_rejection = code.reject(
        user_confirmed=True,
        expected_version=1,
        reason="迟到的拒绝",
        now=datetime(2026, 8, 30, 10, 1, tzinfo=UTC),
    )
    stale_memo_confirmation = memo.confirm(
        user_confirmed=True,
        expected_version=1,
        reason="迟到的确认",
        now=datetime(2026, 8, 30, 10, 1, tzinfo=UTC),
    )
    stale_comparison_rejection = comparison.reject(
        user_confirmed=True,
        expected_version=1,
        reason="迟到的拒绝",
        now=datetime(2026, 8, 30, 10, 1, tzinfo=UTC),
    )
    with Session(engine) as session:
        repository = SqliteResearchAnalysisRepository(session)
        assert repository.add_code(stale_code_rejection) == first_code_decision
        assert repository.add_memo(stale_memo_confirmation) == first_memo_decision
        assert repository.add_comparison(stale_comparison_rejection) == (first_comparison_decision)
        session.commit()

    engine.dispose()


def test_repository_round_trips_comparison_evidence_and_next_research_steps() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    comparison = _comparison(_annotation())

    with Session(engine) as session:
        SqliteResearchAnalysisRepository(session).add_comparison(comparison)
        session.commit()

    with Session(engine) as session:
        restored = SqliteResearchAnalysisRepository(session).list_comparisons(
            user_id=_OWNER,
            task_id=_TASK,
        )

    assert restored == (comparison,)
    assert [finding.kind for finding in restored[0].findings] == [
        ComparisonFindingKind.SUPPORT,
        ComparisonFindingKind.COUNTEREXAMPLE,
        ComparisonFindingKind.CONTRADICT,
    ]
    assert restored[0].competing_explanations == ("组织者动员能力差异",)
    assert restored[0].evidence_gaps == ("缺少社区乙组织者的访谈",)
    assert restored[0].next_steps[0].priority == "high"
    engine.dispose()


def test_analysis_migration_matches_the_repository_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'research-analysis.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    command.upgrade(alembic_config, "head")

    engine = create_engine(Settings().database_url)
    expected_tables = {model.__tablename__ for model in _ANALYSIS_MODELS}
    scoped_metadata = MetaData()
    for table_name, primary_key in (
        ("users", "user_id"),
        ("research_tasks", "task_id"),
        ("research_materials", "material_id"),
    ):
        Table(table_name, scoped_metadata, Column(primary_key, String(36), primary_key=True))
    for model in _ANALYSIS_MODELS:
        model.__table__.to_metadata(scoped_metadata)

    def include_analysis_object(
        schema_object: object,
        name: str | None,
        object_type: str,
        _reflected: bool,
        _compare_to: object,
    ) -> bool:
        if object_type == "table":
            return name in expected_tables
        table_name = getattr(getattr(schema_object, "table", None), "name", None)
        return table_name in expected_tables

    try:
        assert all(model.metadata is Base.metadata for model in _ANALYSIS_MODELS)
        with engine.connect() as connection:
            migration_context = MigrationContext.configure(
                connection,
                opts={
                    "compare_type": True,
                    "include_object": include_analysis_object,
                },
            )
            assert compare_metadata(migration_context, scoped_metadata) == []
    finally:
        engine.dispose()
