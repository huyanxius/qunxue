from collections.abc import Callable
from copy import deepcopy
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
PROVENANCE_REQUIRED_SECTION_KEYS = frozenset(
    {
        "theoretical_perspective",
        "core_concepts",
        "mechanisms",
        "questions_or_hypotheses",
        "methodology",
        "analysis_steps",
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


class ResearchDocumentEvidenceSourceKind(StrEnum):
    PUBLIC_KNOWLEDGE = "public_knowledge"
    PERSONAL_MATERIAL = "personal_material"


@dataclass(frozen=True, slots=True)
class ResearchDocumentEvidenceRef:
    evidence_ref_id: str
    source_id: str
    knowledge_release_id: str | None
    source_kind: ResearchDocumentEvidenceSourceKind = (
        ResearchDocumentEvidenceSourceKind.PUBLIC_KNOWLEDGE
    )
    annotation_id: UUID | None = None
    material_id: UUID | None = None
    parse_id: UUID | None = None
    segment_id: str | None = None
    locator: dict[str, object] | None = None

    def __post_init__(self) -> None:
        source_kind = ResearchDocumentEvidenceSourceKind(self.source_kind)
        object.__setattr__(self, "source_kind", source_kind)
        if source_kind is ResearchDocumentEvidenceSourceKind.PUBLIC_KNOWLEDGE:
            if not self.knowledge_release_id or not self.knowledge_release_id.strip():
                raise ValueError("public evidence requires a knowledge release")
            return
        if self.knowledge_release_id is not None:
            raise ValueError("personal material evidence cannot claim a knowledge release")
        if not all(
            (
                self.annotation_id,
                self.material_id,
                self.parse_id,
                self.segment_id and self.segment_id.strip(),
                self.locator,
            )
        ):
            raise ValueError("personal material evidence requires an exact source locator")
        object.__setattr__(self, "segment_id", self.segment_id.strip())
        object.__setattr__(self, "locator", deepcopy(self.locator))


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
    analysis_handoff: dict[str, object] | None = None
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


@dataclass(frozen=True, slots=True)
class ResearchDocumentCompletionCheck:
    code: str
    label: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ResearchDocumentCompletionGate:
    document_id: UUID
    version: int
    ready: bool
    pending_proposal_count: int
    blockers: tuple[str, ...]
    checks: tuple[ResearchDocumentCompletionCheck, ...]


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
        analysis_handoff: dict[str, object] | None = None,
    ) -> ResearchDocumentSnapshot:
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("document title is required")
        release_id = knowledge_release_id.strip()
        if not release_id:
            raise ValueError("knowledge release is required")
        self._validate_sections(sections, release_id=release_id)
        existing = next(
            (
                item
                for item in self._repository.list_for_task(task_id)
                if item.theory_plan_id == theory_plan_id
            ),
            None,
        )
        if existing is not None:
            return existing
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
                analysis_handoff=_analysis_handoff(analysis_handoff),
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
        analysis_handoff: dict[str, object] | None = None,
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
                analysis_handoff=(
                    current.analysis_handoff
                    if analysis_handoff is None
                    else _analysis_handoff(analysis_handoff)
                ),
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

    def completion_gate(
        self,
        *,
        document_id: UUID,
        pending_proposal_count: int = 0,
    ) -> ResearchDocumentCompletionGate:
        current = self.get(document_id)
        section_by_key = {section.key: section for section in current.sections}
        missing = sorted(REQUIRED_FRAMEWORK_SECTION_KEYS - section_by_key.keys())
        unresolved = tuple(
            section
            for section in current.sections
            if section.key in REQUIRED_FRAMEWORK_SECTION_KEYS
            and section.status
            in {
                ResearchDocumentSectionStatus.DRAFT,
                ResearchDocumentSectionStatus.NEEDS_USER_DECISION,
            }
        )
        evidence_gaps = section_by_key.get("evidence_gaps")
        gaps_disclosed = bool(evidence_gaps and evidence_gaps.content.strip())
        missing_provenance = tuple(
            section
            for section in current.sections
            if section.key in PROVENANCE_REQUIRED_SECTION_KEYS
            and not section.evidence_refs
            and section.status is not ResearchDocumentSectionStatus.EVIDENCE_GAP
        )
        blockers = tuple(
            [f"缺少必需章节：{', '.join(missing)}。"] if missing else []
        ) + tuple(f"章节“{section.title}”仍待审阅。" for section in unresolved)
        blockers += tuple(
            f"章节“{section.title}”的关键判断需要引用，或明确标记为证据缺口。"
            for section in missing_provenance
        )
        if pending_proposal_count:
            blockers += (f"还有 {pending_proposal_count} 条 Agent 建议待处理。",)
        if not gaps_disclosed:
            blockers += ("需要明确披露当前证据缺口。",)
        exportable = not blockers
        checks = (
            ResearchDocumentCompletionCheck(
                code="required_sections",
                label="规定内容完整",
                passed=not missing,
                detail=("12 个研究框架章节齐全。" if not missing else blockers[0]),
            ),
            ResearchDocumentCompletionCheck(
                code="section_review",
                label="章节已审阅",
                passed=not unresolved,
                detail=(
                    "所有规定章节均已审阅或明确标记证据缺口。"
                    if not unresolved
                    else "；".join(f"{section.title}仍待审阅" for section in unresolved)
                ),
            ),
            ResearchDocumentCompletionCheck(
                code="latest_version",
                label="已使用最新版本",
                passed=True,
                detail=f"完成检查基于当前最新的第 {current.version} 版。",
            ),
            ResearchDocumentCompletionCheck(
                code="pending_proposals",
                label="Agent 建议已处理",
                passed=pending_proposal_count == 0,
                detail=(
                    "没有待处理的 Agent 建议。"
                    if pending_proposal_count == 0
                    else f"还有 {pending_proposal_count} 条建议待接受或拒绝。"
                ),
            ),
            ResearchDocumentCompletionCheck(
                code="critical_provenance",
                label="关键判断可追溯",
                passed=not missing_provenance,
                detail=(
                    "理论、机制、问题与方法判断均保留引用或明确证据缺口。"
                    if not missing_provenance
                    else "、".join(section.title for section in missing_provenance)
                    + "尚未保留引用或证据缺口标记。"
                ),
            ),
            ResearchDocumentCompletionCheck(
                code="evidence_gaps_disclosed",
                label="证据缺口已披露",
                passed=gaps_disclosed,
                detail=(
                    "证据缺口章节已有明确说明。"
                    if gaps_disclosed
                    else "证据缺口章节不能为空。"
                ),
            ),
            ResearchDocumentCompletionCheck(
                code="exportable",
                label="成果包可导出",
                passed=exportable,
                detail=(
                    "当前最新版本满足正式导出前置条件。"
                    if exportable
                    else "解决以上阻断项后才能生成正式成果包。"
                ),
            ),
        )
        return ResearchDocumentCompletionGate(
            document_id=current.document_id,
            version=current.version,
            ready=exportable,
            pending_proposal_count=pending_proposal_count,
            blockers=blockers,
            checks=checks,
        )

    def confirm(
        self,
        *,
        document_id: UUID,
        expected_version: int,
        pending_proposal_count: int = 0,
        analysis_handoff: dict[str, object] | None = None,
    ) -> ResearchDocumentSnapshot:
        current = self.get(document_id)
        self._assert_current_version(current, expected_version)
        if current.status is ResearchDocumentStatus.CONFIRMED:
            raise ValueError("confirmed document is already final")
        gate = self.completion_gate(
            document_id=document_id,
            pending_proposal_count=pending_proposal_count,
        )
        if not gate.ready:
            missing = REQUIRED_FRAMEWORK_SECTION_KEYS - {
                section.key for section in current.sections
            }
            if missing:
                raise ValueError(
                    "required sections are missing: " + ", ".join(sorted(missing))
                )
            if any(
                section.status is ResearchDocumentSectionStatus.NEEDS_USER_DECISION
                for section in current.sections
            ):
                raise ValueError(
                    "pending user decisions must be resolved before confirmation"
                )
            raise ValueError("completion gate blocked: " + " ".join(gate.blockers))
        now = self._clock()
        candidate = replace(
                current,
                revision_id=self._id_factory(),
                version=current.version + 1,
                status=ResearchDocumentStatus.CONFIRMED,
                change_summary="用户确认正式研究框架",
                actor="user",
                created_at=now,
                analysis_handoff=(
                    current.analysis_handoff
                    if analysis_handoff is None
                    else _analysis_handoff(analysis_handoff)
                ),
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
        latest = self.get(document_id)
        if (
            snapshot.revision_id != latest.revision_id
            or snapshot.status is not ResearchDocumentStatus.CONFIRMED
        ):
            raise ValueError("only the latest confirmed document version can be exported")
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
                (
                    "- "
                    f"`{evidence.evidence_ref_id}` — personal material "
                    f"`{evidence.material_id}`; segment `{evidence.segment_id}`"
                    if evidence.source_kind
                    is ResearchDocumentEvidenceSourceKind.PERSONAL_MATERIAL
                    else "- "
                    f"`{evidence.evidence_ref_id}` — source `{evidence.source_id}`; "
                    f"release `{evidence.knowledge_release_id}`"
                )
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
                evidence.source_kind
                is ResearchDocumentEvidenceSourceKind.PUBLIC_KNOWLEDGE
                and evidence.knowledge_release_id != release_id
                for evidence in section.evidence_refs
            ):
                raise ValueError("evidence must use the document knowledge release")


def _analysis_handoff(value: dict[str, object] | None) -> dict[str, object] | None:
    if value is None:
        return None
    normalized = deepcopy(value)
    if normalized.get("schema_version") != "research-analysis-v1":
        raise ValueError("unsupported research analysis handoff")
    annotations = normalized.get("annotations")
    if not isinstance(annotations, list):
        raise ValueError("research analysis annotations are required")
    if any(isinstance(item, dict) and "quote" in item for item in annotations):
        raise ValueError("research document handoff cannot persist source text")
    return normalized
