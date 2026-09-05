"""Full-material coding orchestration over the existing material and analysis boundaries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
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
        analyzer: Callable | None = None,
        commit: Callable[[], None] | None = None,
    ) -> None:
        self._analyzer = analyzer
        self._commit = commit or (lambda: None)
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
        from qunxue_api.application.research_analysis import ResearchAnalysisApplication

        try:
            if self._analyzer is None:
                raise RuntimeError("coding_model_unavailable")
            run = self._batches.save(run.processing(now=self._clock()))
            self._commit()
            material = self._materials.get(run.material_id, user_id=run.user_id, task_id=run.task_id)
            if material is None:
                raise LookupError(run.material_id)
            if segments is None:
                segments = self._segments(material, user_id=run.user_id, task_id=run.task_id, parse_id=run.parse_id)
            app = ResearchAnalysisApplication(analysis=self.analysis, materials=self._materials,
                research_tasks=self._research_tasks, clock=self._clock())
            while run.processed_segments < len(segments):
                chunk = segments[run.processed_segments:run.processed_segments + 8]
                snapshot = self.analysis.snapshot(user_id=run.user_id, task_id=run.task_id)
                task = self._research_tasks.get(run.task_id, run.user_id)
                context = {
                    "research_question": getattr(task, "phenomenon_research_intent", None),
                    "method": getattr(task, "method_orientation", None),
                    "codes": [{"label": c.label, "definition": c.definition, "status": c.status.value}
                              for c in snapshot["codes"]],
                }
                proposals = tuple(self._analyzer(segments=chunk, context=context,
                    user_id=run.user_id, task_id=run.task_id, run_id=run.run_id))
                by_segment = {block.segment_id: [] for block in chunk}
                for proposal in proposals:
                    block = next((item for item in chunk if item.segment_id == proposal["segment_id"]), None)
                    if block is None:
                        raise ValueError("coding_source_not_in_batch")
                    quote = str(proposal["quote"])
                    start = int(proposal.get("quote_start", block.text.find(quote)))
                    if not quote.strip() or start < 0 or block.text[start:start + len(quote)] != quote:
                        raise ValueError("coding_quote_not_in_source")
                    if any(not str(proposal[key]).strip() for key in ("label", "definition", "rationale")):
                        raise ValueError("coding_interpretation_incomplete")
                    by_segment[block.segment_id].append((proposal, start))
                # Validate every source before persisting this chunk. Each source/label has
                # its own idempotency key; repeated concepts cannot collide with other rows.
                for block in chunk:
                    annotations, codes = list(run.annotation_ids), list(run.code_ids)
                    uncertain = False
                    for index, (proposal, start) in enumerate(by_segment[block.segment_id]):
                        code = app.propose_source_code_from_agent(
                            user_id=run.user_id, task_id=run.task_id, material_id=run.material_id,
                            parse_id=run.parse_id, segment_id=block.segment_id,
                            quote_start=start, quote_end=start + len(str(proposal["quote"])),
                            label=str(proposal["label"]), definition=str(proposal["definition"]),
                            rationale=str(proposal["rationale"]), conversation_id=run.run_id,
                            agent_run_id=run.run_id, agent_turn_id=run.run_id,
                            tool_call_id=f"batch:{run.run_id}:{block.segment_id}:{index}",
                        )
                        annotations.extend(code.annotation_ids)
                        codes.append(code.code_id)
                        uncertain = uncertain or float(proposal.get("confidence", 0)) < 0.65
                    run = self._batches.save(replace(run,
                        processed_segments=run.processed_segments + 1,
                        annotation_ids=tuple(dict.fromkeys(annotations)), code_ids=tuple(dict.fromkeys(codes)),
                        low_confidence_segments=run.low_confidence_segments + ((block.segment_id,) if uncertain else ()),
                        updated_at=self._clock()))
                    self._commit()
            run = self._batches.save(run.complete(now=self._clock()))
        except Exception as error:
            run = self._batches.save(run.fail(error_code=str(error) if str(error) in {
                "coding_model_unavailable", "coding_quote_not_in_source", "coding_source_not_in_batch",
                "coding_interpretation_incomplete"} else type(error).__name__, now=self._clock()))
        self._commit()
        return run

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
