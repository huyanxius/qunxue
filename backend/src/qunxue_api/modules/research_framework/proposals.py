import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Protocol
from uuid import UUID, uuid4

from qunxue_api.modules.research_framework.document import (
    REQUIRED_FRAMEWORK_SECTION_KEYS,
    ResearchDocumentSection,
    ResearchDocumentSectionStatus,
    ResearchDocumentService,
    ResearchDocumentSnapshot,
    ResearchDocumentStatus,
)


class ResearchDocumentProposalKind(StrEnum):
    CREATE = "create"
    REVISE_SECTION = "revise_section"


class ResearchDocumentProposalStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ABORTED = "aborted"


@dataclass(frozen=True, slots=True)
class ResearchDocumentProposalSnapshot:
    proposal_id: UUID
    kind: ResearchDocumentProposalKind
    status: ResearchDocumentProposalStatus
    user_id: UUID
    conversation_id: UUID
    agent_run_id: UUID
    task_id: UUID
    theory_plan_id: UUID
    knowledge_release_id: str
    title: str
    proposed_sections: tuple[ResearchDocumentSection, ...]
    rationale: str
    created_at: datetime
    document_id: UUID | None = None
    base_document_version: int | None = None
    target_section_id: str | None = None
    decision_reason: str | None = None
    decided_at: datetime | None = None
    result_document_id: UUID | None = None
    result_document_version: int | None = None
    request_hash: str = ""
    model_provider: str | None = None
    model_name: str | None = None


@dataclass(frozen=True, slots=True)
class ResearchDocumentProposalAcceptance:
    proposal: ResearchDocumentProposalSnapshot
    document: ResearchDocumentSnapshot


class ResearchDocumentProposalRepository(Protocol):
    def add(
        self, snapshot: ResearchDocumentProposalSnapshot
    ) -> ResearchDocumentProposalSnapshot: ...

    def get(self, proposal_id: UUID) -> ResearchDocumentProposalSnapshot | None: ...

    def save(
        self, snapshot: ResearchDocumentProposalSnapshot
    ) -> ResearchDocumentProposalSnapshot: ...

    def list_for_document(
        self, document_id: UUID
    ) -> tuple[ResearchDocumentProposalSnapshot, ...]: ...

    def list_for_task(
        self, task_id: UUID
    ) -> tuple[ResearchDocumentProposalSnapshot, ...]: ...

    def list_actionable_for_task(
        self, task_id: UUID
    ) -> tuple[ResearchDocumentProposalSnapshot, ...]: ...

    def validate_agent_context(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        agent_run_id: UUID,
        task_id: UUID,
        knowledge_release_id: str,
    ) -> bool: ...

    def find_revision_for_agent_target(
        self,
        *,
        agent_run_id: UUID,
        document_id: UUID,
        base_document_version: int,
        target_section_id: str,
    ) -> ResearchDocumentProposalSnapshot | None: ...

    def find_create_for_theory_plan(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        theory_plan_id: UUID,
    ) -> ResearchDocumentProposalSnapshot | None: ...

    def agent_run_status(self, agent_run_id: UUID) -> str | None: ...

    def agent_run_model(self, agent_run_id: UUID) -> tuple[str, str] | None: ...


class ResearchDocumentProposalService:
    """Agent writes proposals; only this service's explicit accept path mutates a document."""

    def __init__(
        self,
        *,
        repository: ResearchDocumentProposalRepository,
        documents: ResearchDocumentService,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] | None = None,
        atomic: Callable[[], AbstractContextManager[None]] | None = None,
        validate_proposal: Callable[..., None] | None = None,
    ) -> None:
        self._repository = repository
        self._documents = documents
        self._id_factory = id_factory
        self._clock = clock or (lambda: datetime.now(UTC))
        self._atomic = atomic
        self._validate_proposal = validate_proposal

    def propose_revision(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        agent_run_id: UUID,
        document_id: UUID,
        expected_version: int,
        section: ResearchDocumentSection,
        rationale: str,
    ) -> ResearchDocumentProposalSnapshot:
        current = self._documents.get(document_id)
        if current.version != expected_version:
            raise ValueError("stale research document version")
        if current.status is ResearchDocumentStatus.CONFIRMED:
            raise ValueError("confirmed document must be restored before proposal")
        existing = next(
            (
                item
                for item in current.sections
                if item.section_id == section.section_id and item.key == section.key
            ),
            None,
        )
        if existing is None:
            raise ValueError("proposal section is not part of the document")
        self._validate_proposed_sections((section,), release_id=current.knowledge_release_id)
        self._require_agent_context(
            user_id=user_id,
            conversation_id=conversation_id,
            agent_run_id=agent_run_id,
            task_id=current.task_id,
            knowledge_release_id=current.knowledge_release_id,
        )
        model_provider, model_name = self._required_agent_model(agent_run_id)
        self._validate_scope(
            user_id=user_id,
            task_id=current.task_id,
            theory_plan_id=current.theory_plan_id,
            knowledge_release_id=current.knowledge_release_id,
            sections=(section,),
        )
        request_hash = _proposal_hash(
            title=current.title,
            sections=(section,),
            rationale=rationale,
        )
        duplicate = self._repository.find_revision_for_agent_target(
            agent_run_id=agent_run_id,
            document_id=current.document_id,
            base_document_version=current.version,
            target_section_id=section.section_id,
        )
        if duplicate is not None:
            if duplicate.request_hash == request_hash:
                return duplicate
            raise ValueError("Agent run already proposed another revision for this section")
        return self._repository.add(
            ResearchDocumentProposalSnapshot(
                proposal_id=self._id_factory(),
                kind=ResearchDocumentProposalKind.REVISE_SECTION,
                status=ResearchDocumentProposalStatus.PENDING,
                user_id=user_id,
                conversation_id=conversation_id,
                agent_run_id=agent_run_id,
                task_id=current.task_id,
                theory_plan_id=current.theory_plan_id,
                knowledge_release_id=current.knowledge_release_id,
                title=current.title,
                proposed_sections=(section,),
                rationale=self._required_reason(rationale),
                created_at=self._clock(),
                document_id=current.document_id,
                base_document_version=current.version,
                target_section_id=section.section_id,
                request_hash=request_hash,
                model_provider=model_provider,
                model_name=model_name,
            )
        )

    def propose_create(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        agent_run_id: UUID,
        task_id: UUID,
        theory_plan_id: UUID,
        knowledge_release_id: str,
        title: str,
        sections: tuple[ResearchDocumentSection, ...],
        rationale: str,
    ) -> ResearchDocumentProposalSnapshot:
        release_id = knowledge_release_id.strip()
        self._validate_proposed_sections(
            sections,
            release_id=release_id,
            require_complete=True,
        )
        self._require_agent_context(
            user_id=user_id,
            conversation_id=conversation_id,
            agent_run_id=agent_run_id,
            task_id=task_id,
            knowledge_release_id=release_id,
        )
        model_provider, model_name = self._required_agent_model(agent_run_id)
        self._validate_scope(
            user_id=user_id,
            task_id=task_id,
            theory_plan_id=theory_plan_id,
            knowledge_release_id=release_id,
            sections=sections,
        )
        request_hash = _proposal_hash(
            title=title,
            sections=sections,
            rationale=rationale,
        )
        existing = self._repository.find_create_for_theory_plan(
            user_id=user_id,
            task_id=task_id,
            theory_plan_id=theory_plan_id,
        )
        if existing is not None and self._repository.agent_run_status(
            existing.agent_run_id
        ) in {"failed", "interrupted"}:
            archived = replace(
                existing,
                status=ResearchDocumentProposalStatus.ABORTED,
                decision_reason="Agent 运行未完成，本建议已作废；可安全重试原请求。",
                decided_at=self._clock(),
            )
            persisted_archive = self._repository.save(archived)
            if persisted_archive != archived:
                raise ValueError("proposal decision conflict")
            existing = None
        if existing is not None:
            if existing.request_hash == request_hash:
                return existing
            raise ValueError("confirmed theory plan already has an active M5 proposal")
        persisted = self._repository.add(
            ResearchDocumentProposalSnapshot(
                proposal_id=self._id_factory(),
                kind=ResearchDocumentProposalKind.CREATE,
                status=ResearchDocumentProposalStatus.PENDING,
                user_id=user_id,
                conversation_id=conversation_id,
                agent_run_id=agent_run_id,
                task_id=task_id,
                theory_plan_id=theory_plan_id,
                knowledge_release_id=release_id,
                title=title.strip(),
                proposed_sections=sections,
                rationale=self._required_reason(rationale),
                created_at=self._clock(),
                request_hash=request_hash,
                model_provider=model_provider,
                model_name=model_name,
            )
        )
        if persisted.request_hash != request_hash:
            raise ValueError("confirmed theory plan already has an active M5 proposal")
        return persisted

    def get(self, proposal_id: UUID, *, user_id: UUID) -> ResearchDocumentProposalSnapshot:
        snapshot = self._repository.get(proposal_id)
        if snapshot is None or snapshot.user_id != user_id:
            raise LookupError(proposal_id)
        return snapshot

    def list_for_document(
        self, document_id: UUID, *, user_id: UUID
    ) -> tuple[ResearchDocumentProposalSnapshot, ...]:
        snapshots = self._repository.list_for_document(document_id)
        if any(item.user_id != user_id for item in snapshots):
            raise LookupError(document_id)
        return snapshots

    def list_for_task(
        self, task_id: UUID, *, user_id: UUID
    ) -> tuple[ResearchDocumentProposalSnapshot, ...]:
        snapshots = self._repository.list_actionable_for_task(task_id)
        if any(item.user_id != user_id for item in snapshots):
            raise LookupError(task_id)
        return snapshots

    def accept(
        self,
        *,
        proposal_id: UUID,
        user_id: UUID,
        expected_document_version: int | None,
    ) -> ResearchDocumentProposalAcceptance:
        if self._atomic is None:
            return self._accept_impl(
                proposal_id=proposal_id,
                user_id=user_id,
                expected_document_version=expected_document_version,
            )
        with self._atomic():
            return self._accept_impl(
                proposal_id=proposal_id,
                user_id=user_id,
                expected_document_version=expected_document_version,
            )

    def _accept_impl(
        self,
        *,
        proposal_id: UUID,
        user_id: UUID,
        expected_document_version: int | None,
    ) -> ResearchDocumentProposalAcceptance:
        proposal = self.get(proposal_id, user_id=user_id)
        if proposal.status is ResearchDocumentProposalStatus.REJECTED:
            raise ValueError("rejected proposal cannot be accepted")
        if proposal.status is ResearchDocumentProposalStatus.ABORTED:
            raise ValueError("aborted proposal cannot be accepted")
        if proposal.status is ResearchDocumentProposalStatus.ACCEPTED:
            if proposal.result_document_id is None or proposal.result_document_version is None:
                raise RuntimeError("accepted proposal is missing its result document")
            return ResearchDocumentProposalAcceptance(
                proposal=proposal,
                document=self._documents.get(
                    proposal.result_document_id,
                    version=proposal.result_document_version,
                ),
            )
        self._validate_scope(
            user_id=user_id,
            task_id=proposal.task_id,
            theory_plan_id=proposal.theory_plan_id,
            knowledge_release_id=proposal.knowledge_release_id,
            sections=proposal.proposed_sections,
        )
        if self._repository.agent_run_status(proposal.agent_run_id) != "completed":
            raise ValueError("proposal Agent run must complete before user acceptance")
        if proposal.kind is ResearchDocumentProposalKind.CREATE:
            if expected_document_version is not None:
                raise ValueError("new document proposal has no base version")
            self._validate_proposed_sections(
                proposal.proposed_sections,
                release_id=proposal.knowledge_release_id,
                require_complete=True,
            )
            accepted_sections = tuple(
                replace(section, status=ResearchDocumentSectionStatus.REVIEWED)
                if section.status is ResearchDocumentSectionStatus.DRAFT
                else section
                for section in proposal.proposed_sections
            )
            document = self._documents.create(
                task_id=proposal.task_id,
                theory_plan_id=proposal.theory_plan_id,
                knowledge_release_id=proposal.knowledge_release_id,
                title=proposal.title,
                sections=accepted_sections,
                actor="agent_suggestion_accepted",
            )
        else:
            if proposal.document_id is None or proposal.base_document_version is None:
                raise RuntimeError("revision proposal is missing its document target")
            if expected_document_version != proposal.base_document_version:
                raise ValueError("stale research document version")
            current = self._documents.get(proposal.document_id)
            if current.version != expected_document_version:
                raise ValueError("stale research document version")
            replacement = proposal.proposed_sections[0]
            if replacement.status is ResearchDocumentSectionStatus.DRAFT:
                replacement = replace(
                    replacement,
                    status=ResearchDocumentSectionStatus.REVIEWED,
                )
            sections = tuple(
                replacement if item.section_id == replacement.section_id else item
                for item in current.sections
            )
            document = self._documents.revise(
                document_id=current.document_id,
                expected_version=current.version,
                sections=sections,
                change_summary=proposal.rationale,
                actor="agent_suggestion_accepted",
            )
        accepted = replace(
            proposal,
            status=ResearchDocumentProposalStatus.ACCEPTED,
            decision_reason="用户接受 Agent 建议",
            decided_at=self._clock(),
            result_document_id=document.document_id,
            result_document_version=document.version,
            document_id=proposal.document_id or document.document_id,
        )
        persisted = self._repository.save(accepted)
        if persisted != accepted:
            raise ValueError("proposal decision conflict")
        return ResearchDocumentProposalAcceptance(
            proposal=persisted,
            document=document,
        )

    def reject(
        self, *, proposal_id: UUID, user_id: UUID, reason: str
    ) -> ResearchDocumentProposalSnapshot:
        proposal = self.get(proposal_id, user_id=user_id)
        if proposal.status is ResearchDocumentProposalStatus.ACCEPTED:
            raise ValueError("accepted proposal cannot be rejected")
        if proposal.status in {
            ResearchDocumentProposalStatus.REJECTED,
            ResearchDocumentProposalStatus.ABORTED,
        }:
            return proposal
        rejected = replace(
            proposal,
            status=ResearchDocumentProposalStatus.REJECTED,
            decision_reason=self._required_reason(reason),
            decided_at=self._clock(),
        )
        persisted = self._repository.save(rejected)
        if persisted != rejected:
            raise ValueError("proposal decision conflict")
        return persisted

    def _validate_scope(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        theory_plan_id: UUID,
        knowledge_release_id: str,
        sections: tuple[ResearchDocumentSection, ...],
    ) -> None:
        if self._validate_proposal is not None:
            self._validate_proposal(
                user_id=user_id,
                task_id=task_id,
                theory_plan_id=theory_plan_id,
                knowledge_release_id=knowledge_release_id,
                sections=sections,
            )

    @staticmethod
    def _required_reason(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("proposal rationale is required")
        return normalized

    def _require_agent_context(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        agent_run_id: UUID,
        task_id: UUID,
        knowledge_release_id: str,
    ) -> None:
        if not self._repository.validate_agent_context(
            user_id=user_id,
            conversation_id=conversation_id,
            agent_run_id=agent_run_id,
            task_id=task_id,
            knowledge_release_id=knowledge_release_id,
        ):
            raise ValueError("proposal Agent provenance does not match the persisted run")

    def _required_agent_model(self, agent_run_id: UUID) -> tuple[str, str]:
        model = self._repository.agent_run_model(agent_run_id)
        if model is None or not all(value.strip() for value in model):
            raise ValueError("proposal Agent model provenance is missing")
        return model

    @staticmethod
    def _validate_proposed_sections(
        sections: tuple[ResearchDocumentSection, ...],
        *,
        release_id: str,
        require_complete: bool = False,
    ) -> None:
        if not release_id:
            raise ValueError("knowledge release is required")
        if not sections:
            raise ValueError("proposal must include document content")
        for section in sections:
            if not section.content.strip():
                raise ValueError("proposal section content is required")
            if any(item.knowledge_release_id != release_id for item in section.evidence_refs):
                raise ValueError("proposal evidence must use the document knowledge release")
        if not require_complete:
            return

        section_keys = [section.key for section in sections]
        unique_keys = set(section_keys)
        missing = sorted(REQUIRED_FRAMEWORK_SECTION_KEYS - unique_keys)
        unexpected = sorted(unique_keys - REQUIRED_FRAMEWORK_SECTION_KEYS)
        duplicate = len(section_keys) != len(unique_keys)
        if not missing and not unexpected and not duplicate:
            return

        details: list[str] = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected: {', '.join(unexpected)}")
        if duplicate:
            details.append("duplicate section keys are not allowed")
        raise ValueError(
            "create proposal must include exactly the 12 required framework sections; "
            + "; ".join(details)
        )


def _proposal_hash(
    *,
    title: str,
    sections: tuple[ResearchDocumentSection, ...],
    rationale: str,
) -> str:
    payload = {
        "title": title.strip(),
        "rationale": rationale.strip(),
        "sections": [
            {
                "section_id": item.section_id,
                "key": item.key,
                "title": item.title,
                "content": item.content,
                "status": item.status.value,
                "evidence_refs": [
                    {
                        "evidence_ref_id": evidence.evidence_ref_id,
                        "source_id": evidence.source_id,
                        "knowledge_release_id": evidence.knowledge_release_id,
                    }
                    for evidence in item.evidence_refs
                ],
            }
            for item in sections
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"sha256:{sha256(encoded.encode()).hexdigest()}"
