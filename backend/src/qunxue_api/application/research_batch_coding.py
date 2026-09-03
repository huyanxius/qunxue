"""Full-material coding orchestration over the existing material and analysis boundaries."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from qunxue_api.modules.research_analysis import (
    AnalysisAnnotationKind,
    BatchCodingRepository,
    BatchCodingRun,
    BatchCodingStatus,
    ResearchAnalysisService,
)
from qunxue_api.modules.research_materials import MaterialStatus, ResearchMaterial


class BatchMaterialReader(Protocol):
    def get(
        self, material_id: UUID, *, user_id: UUID, task_id: UUID, include_deleted: bool = False
    ) -> ResearchMaterial | None: ...
    def current_segments(
        self, *, user_id: UUID, task_id: UUID, material_id: UUID, parse_id: UUID | None = None
    ): ...


class _MemoryBatchRepository:
    def __init__(self) -> None:
        self.values: dict[UUID, BatchCodingRun] = {}

    def add(self, value: BatchCodingRun) -> BatchCodingRun:
        self.values[value.run_id] = value
        return value

    def get(self, run_id: UUID, *, user_id: UUID, task_id: UUID) -> BatchCodingRun | None:
        value = self.values.get(run_id)
        return value if value and value.user_id == user_id and value.task_id == task_id else None

    def get_by_idempotency(
        self, *, user_id: UUID, task_id: UUID, material_id: UUID, idempotency_key: str
    ) -> BatchCodingRun | None:
        return next(
            (
                value
                for value in self.values.values()
                if value.user_id == user_id
                and value.task_id == task_id
                and value.material_id == material_id
                and value.idempotency_key == idempotency_key
            ),
            None,
        )

    def save(self, value: BatchCodingRun) -> BatchCodingRun:
        self.values[value.run_id] = value
        return value


class ResearchBatchCodingApplication:
    def __init__(
        self,
        *,
        analysis: ResearchAnalysisService,
        materials: BatchMaterialReader,
        research_tasks,
        batches: BatchCodingRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.analysis = analysis
        self._materials = materials
        self._research_tasks = research_tasks
        self._batches = batches or _MemoryBatchRepository()
        self._clock = clock or (lambda: datetime.now(UTC))

    def start(
        self, *, user_id: UUID, task_id: UUID, material_id: UUID, idempotency_key: str
    ) -> BatchCodingRun:
        self._require_task(user_id, task_id)
        existing = self._batches.get_by_idempotency(
            user_id=user_id,
            task_id=task_id,
            material_id=material_id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            if existing.status is BatchCodingStatus.FAILED:
                existing = self._batches.save(existing.retry(now=self._clock()))
            if existing.status is BatchCodingStatus.COMPLETED:
                return existing
            return self._process(existing)
        material = self._materials.get(material_id, user_id=user_id, task_id=task_id)
        if material is None or material.status is not MaterialStatus.READY:
            raise LookupError(material_id)
        if material.current_parse_id is None or material.current_parse_version is None:
            raise ValueError("material has no ready parse")
        segments = self._segments(material, user_id=user_id, task_id=task_id)
        run = BatchCodingRun.queued(
            user_id=user_id,
            task_id=task_id,
            material_id=material_id,
            parse_id=material.current_parse_id,
            parse_version=material.current_parse_version,
            idempotency_key=idempotency_key,
            total_segments=len(segments),
            now=self._clock(),
        )
        return self._process(self._batches.add(run), segments=segments)

    def retry(self, *, user_id: UUID, task_id: UUID, run_id: UUID) -> BatchCodingRun:
        self._require_task(user_id, task_id)
        run = self._batches.get(run_id, user_id=user_id, task_id=task_id)
        if run is None:
            raise LookupError(run_id)
        return self._process(self._batches.save(run.retry(now=self._clock())))

    def get(self, *, user_id: UUID, task_id: UUID, run_id: UUID) -> BatchCodingRun:
        self._require_task(user_id, task_id)
        value = self._batches.get(run_id, user_id=user_id, task_id=task_id)
        if value is None:
            raise LookupError(run_id)
        return value

    def list_for_material(
        self, *, user_id: UUID, task_id: UUID, material_id: UUID
    ) -> tuple[BatchCodingRun, ...]:
        self._require_task(user_id, task_id)
        values = getattr(self._batches, "values", {})
        return tuple(
            value
            for value in values.values()
            if value.user_id == user_id
            and value.task_id == task_id
            and value.material_id == material_id
        )

    def analysis_snapshot(self, *, user_id: UUID, task_id: UUID):
        return self.analysis.snapshot(user_id=user_id, task_id=task_id)

    def _process(self, run: BatchCodingRun, *, segments=None) -> BatchCodingRun:
        try:
            run = self._batches.save(run.processing(now=self._clock()))
            if segments is None:
                material = self._materials.get(
                    run.material_id, user_id=run.user_id, task_id=run.task_id
                )
                if material is None:
                    raise LookupError(run.material_id)
                segments = self._segments(
                    material, user_id=run.user_id, task_id=run.task_id, parse_id=run.parse_id
                )
            by_label: dict[str, list[UUID]] = {}
            for block in segments[run.processed_segments :]:
                low_confidence = len(block.text.strip()) < 24
                annotation = self._create_annotation(run, block, low_confidence)
                label = _open_label(block.text)
                by_label.setdefault(label, []).append(annotation.annotation_id)
                code = self._propose_code(run, label, by_label[label])
                run = self._batches.save(
                    run.progress(
                        processed_segments=run.processed_segments + 1,
                        annotation_id=annotation.annotation_id,
                        code_id=code.code_id,
                        low_confidence=low_confidence,
                        segment_id=block.segment_id,
                        now=self._clock(),
                    )
                )
            return self._batches.save(run.complete(now=self._clock()))
        except Exception as error:
            return self._batches.save(run.fail(error_code=type(error).__name__, now=self._clock()))

    def _create_annotation(self, run, block, low_confidence):
        from qunxue_api.application.research_analysis import ResearchAnalysisApplication

        analysis_app = ResearchAnalysisApplication(
            analysis=self.analysis,
            materials=self._materials,
            research_tasks=self._research_tasks,
            clock=self._clock,
        )
        return analysis_app.create_annotation(
            user_id=run.user_id,
            task_id=run.task_id,
            idempotency_key=f"batch-annotation:{run.run_id}:{block.segment_id}",
            material_id=run.material_id,
            parse_id=run.parse_id,
            segment_id=block.segment_id,
            quote_start=0,
            quote_end=len(block.text),
            annotation_kind=AnalysisAnnotationKind.DESCRIPTIVE,
            note=(
                "批量编码候选；低确定性片段，需用户复核。"
                if low_confidence
                else "批量编码候选；请在原文中复核。"
            ),
        )

    def _propose_code(self, run, label, annotation_ids):
        from qunxue_api.application.research_analysis import ResearchAnalysisApplication

        analysis_app = ResearchAnalysisApplication(
            analysis=self.analysis,
            materials=self._materials,
            research_tasks=self._research_tasks,
            clock=self._clock,
        )
        return analysis_app.propose_code_from_agent(
            user_id=run.user_id,
            task_id=run.task_id,
            label=label,
            definition=f"由整份材料批量遍历得到的开放编码候选：{label}",
            annotation_ids=tuple(annotation_ids),
            rationale="第一阶段逐段开放编码；第二阶段按相同候选标签合并原文证据。",
            conversation_id=run.run_id,
            agent_run_id=run.run_id,
            agent_turn_id=run.run_id,
            tool_call_id=f"batch-code:{run.run_id}:{label}",
        )

    def _require_task(self, user_id, task_id):
        if self._research_tasks.get(task_id, user_id) is None:
            raise LookupError("Research task not found")

    def _segments(self, material, *, user_id, task_id, parse_id=None):
        resolved_parse_id = parse_id or material.current_parse_id
        if hasattr(self._materials, "current_segments"):
            return tuple(
                self._materials.current_segments(
                    user_id=user_id,
                    task_id=task_id,
                    material_id=material.material_id,
                    parse_id=resolved_parse_id,
                )
            )
        parsed = self._materials.get_parse(
            material.material_id, resolved_parse_id, user_id=user_id, task_id=task_id
        )
        if parsed is None:
            raise LookupError(resolved_parse_id)
        return tuple(parsed.blocks)


def _open_label(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    normalized = re.sub(r"[。！？；;,.，、]+$", "", normalized)
    return normalized[:48] or "未命名开放编码"
