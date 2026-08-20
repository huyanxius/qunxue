from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

REQUIRED_FRAMEWORK_SECTION_KEYS = frozenset(
    {
        "research_question",
        "research_object_and_field",
        "theoretical_perspective",
        "core_concepts",
        "mechanisms",
        "questions_or_hypotheses",
        "methodology",
        "sample_and_sources",
        "analysis_steps",
        "ethics",
        "limitations",
        "evidence_gaps",
    }
)


class ResearchDocumentStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"


class ResearchDocumentSectionStatus(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    EVIDENCE_GAP = "evidence_gap"
    NEEDS_USER_DECISION = "needs_user_decision"
    CONFIRMED = "confirmed"


@dataclass(frozen=True, slots=True)
class ResearchDocumentEvidenceRef:
    evidence_ref_id: str
    source_id: str
    knowledge_release_id: str


@dataclass(frozen=True, slots=True)
class ResearchDocumentSection:
    section_id: str
    key: str
    title: str
    content: str
    status: ResearchDocumentSectionStatus
    evidence_refs: tuple[ResearchDocumentEvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class ResearchDocumentSnapshot:
    document_id: UUID
    task_id: UUID
    theory_plan_id: UUID
    knowledge_release_id: str
    revision_id: UUID
    version: int
    title: str
    sections: tuple[ResearchDocumentSection, ...]
    status: ResearchDocumentStatus
    change_summary: str
    actor: str
    created_at: datetime
    restored_from_version: int | None = None
    confirmed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ResearchDocumentMarkdownExport:
    document_id: UUID
    task_id: UUID
    theory_plan_id: UUID
    knowledge_release_id: str
    version: int
    filename: str
    media_type: str
    markdown: str


class ResearchDocumentRepository(Protocol):
    def add(self, snapshot: ResearchDocumentSnapshot) -> ResearchDocumentSnapshot: ...

    def latest(self, document_id: UUID) -> ResearchDocumentSnapshot | None: ...

    def get_version(self, document_id: UUID, version: int) -> ResearchDocumentSnapshot | None: ...

    def list_versions(self, document_id: UUID) -> tuple[ResearchDocumentSnapshot, ...]: ...

    def list_for_task(self, task_id: UUID) -> tuple[ResearchDocumentSnapshot, ...]: ...


class ResearchDocumentService:
    """Owns immutable document versions; Agent suggestions enter only after acceptance."""

    def __init__(
        self,
        *,
        repository: ResearchDocumentRepository,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def create(
        self,
        *,
        task_id: UUID,
        theory_plan_id: UUID,
        knowledge_release_id: str,
        title: str,
        sections: tuple[ResearchDocumentSection, ...],
        actor: str = "user",
    ) -> ResearchDocumentSnapshot:
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("document title is required")
        release_id = knowledge_release_id.strip()
        if not release_id:
            raise ValueError("knowledge release is required")
        self._validate_sections(sections, release_id=release_id)
        now = self._clock()
        return self._repository.add(
            ResearchDocumentSnapshot(
                document_id=self._id_factory(),
                task_id=task_id,
                theory_plan_id=theory_plan_id,
                knowledge_release_id=release_id,
                revision_id=self._id_factory(),
                version=1,
                title=normalized_title,
                sections=sections,
                status=ResearchDocumentStatus.DRAFT,
                change_summary="创建研究框架草稿",
                actor=actor.strip() or "user",
                created_at=now,
            )
        )

    def get(self, document_id: UUID, *, version: int | None = None) -> ResearchDocumentSnapshot:
        snapshot = (
            self._repository.latest(document_id)
            if version is None
            else self._repository.get_version(document_id, version)
        )
        if snapshot is None:
            raise LookupError(document_id)
        return snapshot

    def list_versions(self, document_id: UUID) -> tuple[ResearchDocumentSnapshot, ...]:
        versions = self._repository.list_versions(document_id)
        if not versions:
            raise LookupError(document_id)
        return versions

    def list_for_task(self, task_id: UUID) -> tuple[ResearchDocumentSnapshot, ...]:
        return self._repository.list_for_task(task_id)

    def revise(
        self,
        *,
        document_id: UUID,
        expected_version: int,
        sections: tuple[ResearchDocumentSection, ...],
        change_summary: str,
        actor: str,
    ) -> ResearchDocumentSnapshot:
        current = self.get(document_id)
        self._assert_current_version(current, expected_version)
        if current.status is ResearchDocumentStatus.CONFIRMED:
            raise ValueError("confirmed document must be restored before revision")
        self._validate_sections(sections, release_id=current.knowledge_release_id)
        summary = change_summary.strip()
        if not summary:
            raise ValueError("change summary is required")
        candidate = replace(
                current,
                revision_id=self._id_factory(),
                version=current.version + 1,
                sections=sections,
                change_summary=summary,
                actor=actor.strip() or "user",
                created_at=self._clock(),
                restored_from_version=None,
            )
        persisted = self._repository.add(candidate)
        if persisted.revision_id != candidate.revision_id:
            raise ValueError("stale research document version")
        return persisted

    def restore(
        self,
        *,
        document_id: UUID,
        source_version: int,
        expected_version: int,
        reason: str,
    ) -> ResearchDocumentSnapshot:
        current = self.get(document_id)
        self._assert_current_version(current, expected_version)
        source = self.get(document_id, version=source_version)
        summary = reason.strip()
        if not summary:
            raise ValueError("restore reason is required")
        candidate = replace(
                source,
                revision_id=self._id_factory(),
                version=current.version + 1,
                status=ResearchDocumentStatus.DRAFT,
                change_summary=summary,
                actor="user",
                created_at=self._clock(),
                restored_from_version=source_version,
                confirmed_at=None,
            )
        persisted = self._repository.add(candidate)
        if persisted.revision_id != candidate.revision_id:
            raise ValueError("stale research document version")
        return persisted

    def confirm(self, *, document_id: UUID, expected_version: int) -> ResearchDocumentSnapshot:
        current = self.get(document_id)
        self._assert_current_version(current, expected_version)
        if current.status is ResearchDocumentStatus.CONFIRMED:
            raise ValueError("confirmed document is already final")
        section_keys = {section.key for section in current.sections}
        missing = REQUIRED_FRAMEWORK_SECTION_KEYS - section_keys
        if missing:
            raise ValueError("required sections are missing: " + ", ".join(sorted(missing)))
        if any(
            section.status is ResearchDocumentSectionStatus.NEEDS_USER_DECISION
            for section in current.sections
        ):
            raise ValueError("pending user decisions must be resolved before confirmation")
        now = self._clock()
        candidate = replace(
                current,
                revision_id=self._id_factory(),
                version=current.version + 1,
                status=ResearchDocumentStatus.CONFIRMED,
                change_summary="用户确认正式研究框架",
                actor="user",
                created_at=now,
                restored_from_version=None,
                confirmed_at=now,
            )
        persisted = self._repository.add(candidate)
        if persisted.revision_id != candidate.revision_id:
            raise ValueError("stale research document version")
        return persisted

    def export_markdown(
        self, *, document_id: UUID, version: int | None = None
    ) -> ResearchDocumentMarkdownExport:
        snapshot = self.get(document_id, version=version)
        if snapshot.status is not ResearchDocumentStatus.CONFIRMED:
            raise ValueError("only a confirmed document version can be exported")
        metadata = (
            "---\n"
            f"document_id: {snapshot.document_id}\n"
            f"task_id: {snapshot.task_id}\n"
            f"theory_plan_id: {snapshot.theory_plan_id}\n"
            f"knowledge_release_id: {snapshot.knowledge_release_id}\n"
            f"version: {snapshot.version}\n"
            "---\n\n"
        )
        def render_section(section: ResearchDocumentSection) -> str:
            rendered = f"## {section.title}\n\n{section.content.strip()}"
            if not section.evidence_refs:
                return rendered
            evidence_lines = "\n".join(
                "- "
                f"`{evidence.evidence_ref_id}` — source `{evidence.source_id}`; "
                f"release `{evidence.knowledge_release_id}`"
                for evidence in section.evidence_refs
            )
            return f"{rendered}\n\n### 证据引用\n\n{evidence_lines}"

        body = "\n\n".join(render_section(section) for section in snapshot.sections)
        markdown = f"{metadata}# {snapshot.title}\n\n{body}\n"
        return ResearchDocumentMarkdownExport(
            document_id=snapshot.document_id,
            task_id=snapshot.task_id,
            theory_plan_id=snapshot.theory_plan_id,
            knowledge_release_id=snapshot.knowledge_release_id,
            version=snapshot.version,
            filename=f"research-framework-v{snapshot.version}.md",
            media_type="text/markdown",
            markdown=markdown,
        )

    @staticmethod
    def _assert_current_version(snapshot: ResearchDocumentSnapshot, expected_version: int) -> None:
        if snapshot.version != expected_version:
            raise ValueError("stale research document version")

    @staticmethod
    def _validate_sections(
        sections: tuple[ResearchDocumentSection, ...], *, release_id: str
    ) -> None:
        if not sections:
            raise ValueError("at least one document section is required")
        ids = [section.section_id for section in sections]
        keys = [section.key for section in sections]
        if len(ids) != len(set(ids)) or len(keys) != len(set(keys)):
            raise ValueError("document section IDs and keys must be unique")
        for section in sections:
            if not section.section_id.strip() or not section.key.strip():
                raise ValueError("document section identity is required")
            if not section.title.strip() or not section.content.strip():
                raise ValueError("document section title and content are required")
            if any(
                evidence.knowledge_release_id != release_id for evidence in section.evidence_refs
            ):
                raise ValueError("evidence must use the document knowledge release")
