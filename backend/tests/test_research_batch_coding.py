from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from qunxue_api.application.research_batch_coding import ResearchBatchCodingApplication
from qunxue_api.modules.research_analysis import ResearchAnalysisService
from qunxue_api.modules.research_materials import (
    MaterialBlock,
    MaterialKind,
    MaterialLocator,
    MaterialStatus,
    ResearchMaterial,
)


class Tasks:
    def __init__(self, user_id, task_id):
        self.user_id, self.task_id = user_id, task_id

    def get(self, task_id, user_id):
        return object() if (task_id, user_id) == (self.task_id, self.user_id) else None


class Materials:
    def __init__(self, material, blocks):
        self.material, self.blocks = material, blocks

    def get(self, material_id, *, user_id, task_id, include_deleted=False):
        return (
            self.material
            if (material_id, user_id, task_id)
            == (self.material.material_id, self.material.user_id, self.material.task_id)
            else None
        )

    def current_segments(self, *, user_id, task_id, material_id, parse_id=None):
        return self.blocks

    def get_segment(self, material_id, parse_id, segment_id, *, user_id, task_id):
        return next(
            (
                block
                for block in self.blocks
                if block.segment_id == segment_id and block.parse_id == parse_id
            ),
            None,
        )


def context():
    user_id, task_id, material_id, parse_id = (uuid4() for _ in range(4))
    now = datetime.now(UTC)
    material = ResearchMaterial.create(
        material_id=material_id,
        user_id=user_id,
        task_id=task_id,
        idempotency_key="upload",
        original_filename="访谈.txt",
        media_type="text/plain",
        content="访谈".encode(),
        material_kind=MaterialKind.INTERVIEW_TRANSCRIPT,
        now=now,
    )
    blocks = tuple(
        MaterialBlock.create(
            material_id=material_id,
            parse_id=parse_id,
            ordinal=index,
            kind="paragraph",
            text=text,
            locator=MaterialLocator(paragraph=index + 1, char_start=0, char_end=len(text)),
        )
        for index, text in enumerate(
            ("照护责任由姐姐承担。", "弟弟提供经济支持。", "两人都感到疲惫。")
        )
    )
    return (
        user_id,
        task_id,
        replace(
            material,
            status=MaterialStatus.READY,
            current_parse_id=parse_id,
            current_parse_version=1,
        ),
        blocks,
    )


def analyze(**kwargs):
    return tuple({"segment_id": block.segment_id, "quote": block.text, "label": "照护安排", "definition": "家庭成员对照护任务的协商与分配。", "rationale": "此处说明成员承担的责任。", "confidence": 0.7} for block in kwargs["segments"])


def test_batch_coding_walks_every_segment_and_stays_candidate():
    user_id, task_id, material, blocks = context()
    app = ResearchBatchCodingApplication(
        analysis=ResearchAnalysisService.in_memory(),
        analyzer=analyze,
        materials=Materials(material, blocks),
        research_tasks=Tasks(user_id, task_id),
    )

    run = app.start(
        user_id=user_id,
        task_id=task_id,
        material_id=material.material_id,
        idempotency_key="batch-1",
    )

    assert run.status.value == "completed"
    assert run.total_segments == 3
    assert run.processed_segments == 3
    assert len(run.annotation_ids) == 3
    assert len(run.code_ids) == 3
    snapshot = app.analysis_snapshot(user_id=user_id, task_id=task_id)
    assert len(snapshot["annotations"]) == 3
    assert all(code.status.value == "candidate" for code in snapshot["codes"])


def test_batch_start_is_idempotent_for_same_material_version():
    user_id, task_id, material, blocks = context()
    app = ResearchBatchCodingApplication(
        analysis=ResearchAnalysisService.in_memory(),
        analyzer=analyze,
        materials=Materials(material, blocks),
        research_tasks=Tasks(user_id, task_id),
    )

    first = app.start(
        user_id=user_id, task_id=task_id, material_id=material.material_id, idempotency_key="same"
    )
    second = app.start(
        user_id=user_id, task_id=task_id, material_id=material.material_id, idempotency_key="same"
    )

    assert second.run_id == first.run_id
    assert second.annotation_ids == first.annotation_ids


def test_batch_rejects_material_without_current_parse():
    user_id, task_id, material, _ = context()
    material = replace(material, current_parse_id=None)
    app = ResearchBatchCodingApplication(
        analysis=ResearchAnalysisService.in_memory(),
        analyzer=analyze,
        materials=Materials(material, ()),
        research_tasks=Tasks(user_id, task_id),
    )

    with pytest.raises(ValueError, match="parse"):
        app.start(
            user_id=user_id,
            task_id=task_id,
            material_id=material.material_id,
            idempotency_key="no-parse",
        )


def test_batch_does_not_fabricate_codes_when_model_is_unavailable():
    user_id, task_id, material, blocks = context()
    app = ResearchBatchCodingApplication(analysis=ResearchAnalysisService.in_memory(), materials=Materials(material, blocks), research_tasks=Tasks(user_id, task_id))
    result = app.start(user_id=user_id, task_id=task_id, material_id=material.material_id, idempotency_key="unavailable")
    assert result.status.value == "failed"
    assert app.analysis_snapshot(user_id=user_id, task_id=task_id)["codes"] == ()


def test_model_can_skip_irrelevant_text_without_inventing_a_code():
    user_id, task_id, material, blocks = context()
    app = ResearchBatchCodingApplication(analysis=ResearchAnalysisService.in_memory(), materials=Materials(material, blocks), research_tasks=Tasks(user_id, task_id), analyzer=lambda **kw: ())
    result = app.start(user_id=user_id, task_id=task_id, material_id=material.material_id, idempotency_key="skip")
    assert result.status.value == "completed"
    assert result.processed_segments == result.total_segments
    assert result.code_ids == ()


def test_model_quote_must_exist_in_its_segment_before_any_write():
    user_id, task_id, material, blocks = context()
    def fabricated(**kwargs):
        return ({**analyze(**kwargs)[0], "quote": "原文并没有这句话"},)
    app = ResearchBatchCodingApplication(analysis=ResearchAnalysisService.in_memory(), materials=Materials(material, blocks), research_tasks=Tasks(user_id, task_id), analyzer=fabricated)
    result = app.start(user_id=user_id, task_id=task_id, material_id=material.material_id, idempotency_key="bad-quote")
    assert result.status.value == "failed"
    assert app.analysis_snapshot(user_id=user_id, task_id=task_id)["annotations"] == ()


def test_same_model_label_across_segments_finishes_without_idempotency_conflict():
    user_id, task_id, material, blocks = context()
    app = ResearchBatchCodingApplication(analysis=ResearchAnalysisService.in_memory(), materials=Materials(material, blocks), research_tasks=Tasks(user_id, task_id), analyzer=analyze)
    result = app.start(user_id=user_id, task_id=task_id, material_id=material.material_id, idempotency_key="shared-concept")
    assert result.status.value == "completed"
    assert len(app.analysis_snapshot(user_id=user_id, task_id=task_id)["annotations"]) == 3
    assert all(code.label == "照护安排" for code in app.analysis_snapshot(user_id=user_id, task_id=task_id)["codes"])
