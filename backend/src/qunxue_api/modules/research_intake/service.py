import re
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from qunxue_api.modules.research_intake.domain import (
    ConfirmedPhenomenonSnapshot,
    DirectPhenomenonInput,
    EntryType,
    MaterialIntakeRun,
    PhenomenonCandidate,
    PhenomenonCandidateDraft,
    PhenomenonEvidenceRefSnapshot,
    PhenomenonEvidenceVerificationStatus,
    PhenomenonExample,
    PhenomenonModelSnapshot,
    PhenomenonProgress,
    PreparedPhenomenonCandidate,
    ResearchTask,
    ResearchTaskStatus,
)
from qunxue_api.modules.research_intake.errors import ResearchTaskNotFound
from qunxue_api.modules.research_intake.ports import (
    PhenomenonRepository,
    ResearchTaskRepository,
)


class ResearchTaskService:
    def __init__(
        self,
        repository: ResearchTaskRepository,
        *,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def create(
        self,
        *,
        user_id: UUID,
        entry_type: EntryType,
        idempotency_key: str,
        seed_theory_id: str | None = None,
        seed_theory_name: str | None = None,
    ) -> ResearchTask:
        task = ResearchTask.create(
            task_id=self._id_factory(),
            user_id=user_id,
            entry_type=entry_type,
            idempotency_key=idempotency_key,
            seed_theory_id=seed_theory_id,
            seed_theory_name=seed_theory_name,
            now=self._clock(),
        )
        return self._repository.add_or_get_by_idempotency_key(task)

    def get(self, task_id: UUID, *, user_id: UUID) -> ResearchTask:
        task = self._repository.get(task_id, user_id)
        if task is None:
            raise ResearchTaskNotFound(str(task_id))
        return task

    def list_for_user(self, user_id: UUID, *, limit: int) -> list[ResearchTask]:
        return self._repository.list_for_user(user_id, limit=limit)

    def delete(self, task_id: UUID, *, user_id: UUID) -> ResearchTask:
        task = self._repository.delete(task_id, user_id)
        if task is None:
            raise ResearchTaskNotFound(str(task_id))
        return task

    def save_progress(self, task: ResearchTask) -> ResearchTask | None:
        return self._repository.save_progress(task)


class PhenomenonService:
    def __init__(
        self,
        repository: PhenomenonRepository,
        research_tasks: ResearchTaskRepository,
        *,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._research_tasks = research_tasks
        self._id_factory = id_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def list_examples(self) -> list[PhenomenonExample]:
        return self._repository.list_examples()

    def submit_material(
        self,
        *,
        task_id: UUID,
        task: ResearchTask,
        idempotency_key: str,
        filename: str,
        media_type: str,
        text: str,
        research_intent: str | None,
        context: str | None,
        processing_policy_version: str,
        model: PhenomenonModelSnapshot,
    ) -> MaterialIntakeRun:
        run_id = self._id_factory()
        segments = [
            segment.strip()
            for segment in re.split(r"\n\s*\n|\n", text)
            if segment.strip()
        ][:5]
        if not segments:
            raise ValueError("material contains no readable text")
        prepared: list[PreparedPhenomenonCandidate] = []
        prompts = (
            "材料所述现象在不同时间或情境中如何变化？",
            "材料中对同一现象的经历有哪些异同？",
            "材料所述现象在什么条件下持续或中断？",
        )
        candidate_count = min(5, max(3, len(segments)))
        for index in range(candidate_count):
            source_index = min(index, len(segments) - 1)
            excerpt = segments[source_index][:1000]
            phenomenon = excerpt if index < len(segments) else prompts[index % len(prompts)]
            source_ref_id = f"material:{run_id}"
            prepared.append(
                PreparedPhenomenonCandidate(
                    candidate_id=self._id_factory(),
                    draft=PhenomenonCandidateDraft(
                        phenomenon=phenomenon,
                        research_intent=research_intent,
                        context=context,
                        source_ref_ids=(source_ref_id,),
                    ),
                    evidence_refs=(
                        PhenomenonEvidenceRefSnapshot(
                            evidence_ref_id=f"{source_ref_id}:paragraph:{source_index + 1}",
                            excerpt=excerpt,
                            source_ref_id=source_ref_id,
                            source_description=filename,
                            locator=f"第{source_index + 1}段",
                            verification_status=(
                                PhenomenonEvidenceVerificationStatus.USER_ATTESTED
                            ),
                            use_boundary="来自用户确认可处理的去标识化材料，尚未经外部核验。",
                        ),
                    ),
                    missing_information=(
                        "现象发生的时间范围",
                        "可比较的情境或参与者差异",
                    ),
                )
            )
        run = self._repository.submit_material(
            run_id=run_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            filename=filename,
            media_type=media_type,
            processing_policy_version=processing_policy_version,
            candidates=tuple(prepared),
            model=model,
            now=self._clock(),
        )
        if task.current_material_intake_run_id != run.run_id:
            saved = self._research_tasks.save_progress(
                replace(
                    task,
                    version=task.version + 1,
                    updated_at=run.accepted_at,
                    current_phenomenon_candidate_id=run.candidates[0].candidate_id,
                    current_material_intake_run_id=run.run_id,
                )
            )
            if saved is None:
                raise RuntimeError("owned research task disappeared during material intake")
        return run

    def get_material_run(
        self,
        run_id: UUID,
        *,
        user_id: UUID,
    ) -> MaterialIntakeRun | None:
        return self._repository.get_material_run(run_id, user_id)

    def submit_direct(
        self,
        *,
        task_id: UUID,
        phenomenon: str,
        research_intent: str | None,
        context: str | None,
    ) -> DirectPhenomenonInput:
        return self._repository.submit_direct(
            task_id=task_id,
            phenomenon=phenomenon.strip(),
            research_intent=research_intent,
            context=context,
            now=self._clock(),
            input_id=self._id_factory(),
        )

    def input_for_task(self, task_id: UUID) -> DirectPhenomenonInput | None:
        return self._repository.input_for_task(task_id)

    def save_candidate(
        self,
        *,
        task_id: UUID,
        task: ResearchTask,
        draft: PhenomenonCandidateDraft,
        evidence_refs: tuple[PhenomenonEvidenceRefSnapshot, ...],
        model: PhenomenonModelSnapshot,
    ) -> PhenomenonCandidate:
        now = self._clock()
        candidate = self._repository.save_candidate(
            task_id=task_id,
            candidate_id=self._id_factory(),
            draft=draft,
            evidence_refs=evidence_refs,
            model=model,
            now=now,
        )
        saved = self._research_tasks.save_progress(
            replace(
                task,
                version=task.version + 1,
                updated_at=now,
                current_phenomenon_candidate_id=candidate.candidate_id,
            )
        )
        if saved is None:
            raise RuntimeError("owned research task disappeared during candidate generation")
        return candidate

    def get_candidate(
        self, task_id: UUID, candidate_id: UUID, version: int | None = None
    ) -> PhenomenonCandidate | None:
        return self._repository.get_candidate(task_id, candidate_id, version)

    def update_candidate(
        self,
        *,
        task_id: UUID,
        task: ResearchTask,
        candidate_id: UUID,
        expected_version: int,
        phenomenon: str,
        research_intent: str | None,
        context: str | None,
    ) -> PhenomenonCandidate | None:
        now = self._clock()
        candidate = self._repository.update_candidate(
            task_id=task_id,
            candidate_id=candidate_id,
            expected_version=expected_version,
            phenomenon=phenomenon,
            research_intent=research_intent,
            context=context,
            now=now,
        )
        if candidate is None:
            return None
        saved = self._research_tasks.save_progress(
            replace(
                task,
                version=task.version + 1,
                updated_at=now,
                current_phenomenon_candidate_id=candidate.candidate_id,
            )
        )
        if saved is None:
            raise RuntimeError("owned research task disappeared during candidate update")
        return candidate

    def confirm_candidate(
        self,
        *,
        task_id: UUID,
        candidate_id: UUID,
        expected_version: int,
        task: ResearchTask,
    ) -> tuple[ConfirmedPhenomenonSnapshot, datetime] | None:
        result = self._repository.confirm_candidate(
            task_id=task_id,
            candidate_id=candidate_id,
            expected_version=expected_version,
            query_id=self._id_factory(),
            now=self._clock(),
        )
        if result is None:
            return None
        snapshot, confirmed_at = result
        saved_task = self._research_tasks.save_progress(
            replace(
                task,
                status=ResearchTaskStatus.PHENOMENON_CONFIRMED,
                version=task.version + 1,
                updated_at=confirmed_at,
                phenomenon_query_id=snapshot.phenomenon_query_id,
                phenomenon_version=snapshot.version,
                phenomenon_summary=snapshot.phenomenon,
                phenomenon_research_intent=snapshot.research_intent,
                current_phenomenon_candidate_id=candidate_id,
            )
        )
        if saved_task is None:
            raise RuntimeError("owned research task disappeared during confirmation")
        return result

    def progress(self, task_id: UUID) -> PhenomenonProgress:
        return self._repository.progress(task_id)
