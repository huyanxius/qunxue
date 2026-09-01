from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from qunxue_api.adapters.research_exchange import QunxueResearchProjectSnapshot, map_to_qdpx
from qunxue_api.modules.research_analysis import (
    AnalysisAnnotation,
    AnalysisAnnotationKind,
    AnalysisCode,
    AnalysisMemo,
    AnalysisMemoKind,
    CodebookEntry,
)
from qunxue_api.modules.research_intake import EntryType, ResearchTask
from qunxue_api.modules.research_materials import (
    MaterialBlock,
    MaterialCollection,
    MaterialKind,
    MaterialLocator,
    MaterialParseVersion,
    MaterialRelation,
    MaterialRelationType,
    ProfessionalMaterialArchive,
    ResearchCase,
    ResearchMaterial,
)

NOW = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
USER_ID = UUID("30000000-0000-4000-8000-000000000001")
TASK_ID = UUID("30000000-0000-4000-8000-000000000002")
MATERIAL_ID = UUID("30000000-0000-4000-8000-000000000003")
SECOND_MATERIAL_ID = UUID("30000000-0000-4000-8000-000000000004")
PARSE_ID = UUID("30000000-0000-4000-8000-000000000005")
ANNOTATION_ID = UUID("30000000-0000-4000-8000-000000000006")
CODE_ID = UUID("30000000-0000-4000-8000-000000000007")
CANDIDATE_CODE_ID = UUID("30000000-0000-4000-8000-000000000008")
MEMO_ID = UUID("30000000-0000-4000-8000-000000000009")
CASE_ID = UUID("30000000-0000-4000-8000-00000000000a")
COLLECTION_ID = UUID("30000000-0000-4000-8000-00000000000b")
RELATION_ID = UUID("30000000-0000-4000-8000-00000000000c")


def _snapshot() -> QunxueResearchProjectSnapshot:
    task = ResearchTask.create(
        task_id=TASK_ID,
        user_id=USER_ID,
        entry_type=EntryType.DIRECT_INPUT,
        idempotency_key="project",
        project_title="城中村流动与邻里关系",
        seed_theory_id=None,
        seed_theory_name=None,
        now=NOW,
    )
    material = ResearchMaterial.create(
        material_id=MATERIAL_ID,
        user_id=USER_ID,
        task_id=TASK_ID,
        idempotency_key="material-1",
        original_filename="访谈01.txt",
        media_type="text/plain",
        content="通勤时间缩短了，但邻里互助也变少了。".encode(),
        material_kind=MaterialKind.INTERVIEW_TRANSCRIPT,
        now=NOW,
    )
    second_material = ResearchMaterial.create(
        material_id=SECOND_MATERIAL_ID,
        user_id=USER_ID,
        task_id=TASK_ID,
        idempotency_key="material-2",
        original_filename="观察笔记.txt",
        media_type="text/plain",
        content="晚高峰时，巷口聚集的人比上午多。".encode(),
        material_kind=MaterialKind.FIELD_NOTE,
        now=NOW,
    )
    block = MaterialBlock.create(
        parse_id=PARSE_ID,
        material_id=MATERIAL_ID,
        ordinal=0,
        kind="paragraph",
        text="通勤时间缩短了，但邻里互助也变少了。",
        locator=MaterialLocator(paragraph=1, char_start=0, char_end=20),
    )
    parsed = MaterialParseVersion.create(
        parse_id=PARSE_ID,
        material_id=MATERIAL_ID,
        version=3,
        parser_name="plain-text",
        parser_version="1.0",
        schema_version="material-v1",
        full_text=block.text,
        structured_document={"format": "text"},
        blocks=(block,),
        now=NOW,
    )
    material = material.begin_reparse(parse_id=PARSE_ID, now=NOW).record_parse_success(parsed)
    quote = "通勤时间缩短了"
    annotation = AnalysisAnnotation.create(
        annotation_id=ANNOTATION_ID,
        user_id=USER_ID,
        task_id=TASK_ID,
        material_id=MATERIAL_ID,
        parse_id=PARSE_ID,
        segment_id=block.segment_id,
        segment_content_hash=block.content_hash,
        quote=quote,
        quote_start=0,
        quote_end=len(quote),
        locator=block.locator,
        annotation_kind=AnalysisAnnotationKind.DESCRIPTIVE,
        note="受访者把迁居描述为通勤收益。",
        now=NOW,
    )
    confirmed_code = AnalysisCode.candidate(
        code_id=CODE_ID,
        user_id=USER_ID,
        task_id=TASK_ID,
        label="通勤改善",
        definition="迁居后通勤耗时下降。",
        annotation_ids=(ANNOTATION_ID,),
        rationale="原文明确描述通勤时间缩短。",
        source="user",
        now=NOW,
    ).confirm(
        user_confirmed=True,
        expected_version=1,
        reason="研究者核对原文后确认",
        now=NOW,
    )
    candidate_code = AnalysisCode.candidate(
        code_id=CANDIDATE_CODE_ID,
        user_id=USER_ID,
        task_id=TASK_ID,
        label="社区疏离",
        definition="邻里互动减少。",
        annotation_ids=(ANNOTATION_ID,),
        rationale="仍需更多访谈交叉核对。",
        source="agent",
        now=NOW,
    )
    memo = AnalysisMemo.create_candidate(
        memo_id=MEMO_ID,
        user_id=USER_ID,
        task_id=TASK_ID,
        title="迁居的双重效应",
        content="通勤收益可能伴随邻里互助减弱。",
        memo_kind=AnalysisMemoKind.ANALYTIC,
        annotation_ids=(ANNOTATION_ID,),
        code_ids=(CODE_ID,),
        source="user",
        now=NOW,
    ).confirm(
        user_confirmed=True,
        expected_version=1,
        reason="保留为正式分析备忘",
        now=NOW,
    )
    codebook = CodebookEntry.create(
        user_id=USER_ID,
        task_id=TASK_ID,
        code_id=CODE_ID,
        inclusion_rules=("明确提到通勤耗时减少",),
        exclusion_rules=("只提到距离变化但未提到耗时",),
        parent_code_id=None,
        positive_example_annotation_ids=(ANNOTATION_ID,),
        negative_example_annotation_ids=(UUID(int=99),),
        now=NOW,
    )
    collection = MaterialCollection.create(
        collection_id=COLLECTION_ID,
        user_id=USER_ID,
        task_id=TASK_ID,
        name="第一轮田野",
        now=NOW,
    )
    case = ResearchCase.create(
        case_id=CASE_ID,
        user_id=USER_ID,
        task_id=TASK_ID,
        name="受访者01",
        attributes={"职业": "服务业", "迁入年数": 1},
        material_ids=(MATERIAL_ID,),
        now=NOW,
    )
    relation = MaterialRelation.create(
        relation_id=RELATION_ID,
        user_id=USER_ID,
        task_id=TASK_ID,
        source_material_id=SECOND_MATERIAL_ID,
        target_material_id=MATERIAL_ID,
        relation_type=MaterialRelationType.SUPPLEMENTS,
        note="观察记录补充访谈中的巷口交往情境。",
        now=NOW,
    )
    return QunxueResearchProjectSnapshot(
        task=task,
        materials=(material, second_material),
        original_contents={SECOND_MATERIAL_ID: "晚高峰时，巷口聚集的人比上午多。".encode()},
        parses=(parsed,),
        archive=ProfessionalMaterialArchive(
            collections=(collection,),
            cases=(case,),
            relations=(relation,),
        ),
        annotations=(annotation,),
        codes=(confirmed_code, candidate_code),
        memos=(memo,),
        codebook_entries=(codebook,),
    )


def test_public_contract_mapping_keeps_stable_ids_and_reports_native_semantic_loss() -> None:
    mapping = map_to_qdpx(_snapshot())

    assert mapping.project.project_id == TASK_ID
    assert {source.source_id for source in mapping.project.sources} == {
        MATERIAL_ID,
        SECOND_MATERIAL_ID,
    }
    first_source = next(
        source for source in mapping.project.sources if source.source_id == MATERIAL_ID
    )
    assert first_source.selections[0].selection_id == ANNOTATION_ID
    assert first_source.selections[0].codings[0].code_id == CODE_ID
    assert {code.code_id for code in mapping.project.codes} == {CODE_ID}
    assert mapping.project.memos[0].memo_id == MEMO_ID
    assert mapping.project.cases[0].case_id == CASE_ID
    assert mapping.project.sets[0].set_id == COLLECTION_ID
    assert mapping.project.links[0].link_id == RELATION_ID

    losses = {(loss.object_type, loss.object_id, loss.field) for loss in mapping.report.losses}
    assert ("analysis_code", str(CANDIDATE_CODE_ID), "status") in losses
    assert ("analysis_code", str(CODE_ID), "version") in losses
    assert ("material_parse", str(PARSE_ID), "version") in losses
    assert mapping.recovery_manifest["task"]["task_id"] == str(TASK_ID)
    assert mapping.recovery_manifest["analysis"]["codes"][1]["code_id"] == str(CANDIDATE_CODE_ID)


def test_published_media_transcript_is_exported_as_text_with_explicit_locator_loss() -> None:
    snapshot = _snapshot()
    media = ResearchMaterial.create(
        material_id=MATERIAL_ID,
        user_id=USER_ID,
        task_id=TASK_ID,
        idempotency_key="media-1",
        original_filename="访谈01.m4a",
        media_type="audio/mp4",
        content=b"synthetic-media",
        material_kind=MaterialKind.INTERVIEW_TRANSCRIPT,
        now=NOW,
    )
    block = MaterialBlock.create(
        parse_id=PARSE_ID,
        material_id=MATERIAL_ID,
        ordinal=0,
        kind="transcript_segment",
        text="通勤时间缩短了，但邻里互助也变少了。",
        locator=MaterialLocator(time_start_ms=1_000, time_end_ms=4_500, speaker="受访者"),
    )
    parsed = MaterialParseVersion.create(
        parse_id=PARSE_ID,
        material_id=MATERIAL_ID,
        version=1,
        parser_name="published-transcription",
        parser_version="1.0",
        schema_version="material-v1",
        full_text=block.text,
        structured_document={"format": "transcript"},
        blocks=(block,),
        now=NOW,
    )
    media = media.begin_reparse(parse_id=PARSE_ID, now=NOW).record_parse_success(parsed)

    mapping = map_to_qdpx(
        replace(
            snapshot,
            materials=(media,),
            parses=(parsed,),
            original_contents={MATERIAL_ID: b"synthetic-media"},
            archive=ProfessionalMaterialArchive(),
        )
    )

    assert mapping.project.sources[0].plain_text == block.text
    losses = {(loss.object_id, loss.field) for loss in mapping.report.losses}
    assert (str(MATERIAL_ID), "media_payload") in losses
    assert (str(PARSE_ID), "timecodes_and_speakers") in losses
