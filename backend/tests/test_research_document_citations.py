from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from qunxue_api.api.contracts.research_documents import (
    ResearchDocumentSectionContract,
    UpdateResearchDocumentRequest,
)
from qunxue_api.application.research_documents import _export_manifest
from qunxue_api.modules.research_framework import (
    ResearchDocumentCitationKind,
    ResearchDocumentCitationRef,
    ResearchDocumentCitationState,
    ResearchDocumentFormatting,
    ResearchDocumentSection,
    ResearchDocumentSectionStatus,
    ResearchDocumentService,
    ResearchDocumentSnapshot,
    ResearchDocumentStatus,
)


def _citation(
    *,
    citation_id: str = "citation-1",
    kind: ResearchDocumentCitationKind = ResearchDocumentCitationKind.SCHOLARLY,
    state: ResearchDocumentCitationState = ResearchDocumentCitationState.VERIFIED,
) -> ResearchDocumentCitationRef:
    return ResearchDocumentCitationRef(
        citation_id=citation_id,
        kind=kind,
        source_id="literature-entry-1",
        source_version="version-3",
        locator={"label": "page", "value": "42-44"},
        state=state,
    )


def test_structured_citation_keeps_source_version_locator_and_verification_state() -> None:
    citation = _citation()

    assert citation.source_id == "literature-entry-1"
    assert citation.source_version == "version-3"
    assert citation.locator == {"label": "page", "value": "42-44"}
    assert citation.state is ResearchDocumentCitationState.VERIFIED


def test_scholarly_and_empirical_citations_require_an_exact_locator() -> None:
    with pytest.raises(ValueError, match="locator"):
        ResearchDocumentCitationRef(
            citation_id="citation-1",
            kind=ResearchDocumentCitationKind.SCHOLARLY,
            source_id="literature-entry-1",
            source_version="version-3",
            locator=None,
            state=ResearchDocumentCitationState.VERIFIED,
        )

    with pytest.raises(ValueError, match="locator"):
        ResearchDocumentCitationRef(
            citation_id="citation-2",
            kind=ResearchDocumentCitationKind.EMPIRICAL,
            source_id="material-segment-1",
            source_version="parse-2",
            locator={},
            state=ResearchDocumentCitationState.VERIFIED,
        )


def test_unavailable_citations_remain_in_the_version_instead_of_being_dropped() -> None:
    section = ResearchDocumentSection(
        section_id="research-question",
        key="research_question",
        title="研究问题",
        content="迁移如何改变照护分工？",
        status=ResearchDocumentSectionStatus.REVIEWED,
        evidence_refs=(),
        citation_refs=(
            _citation(state=ResearchDocumentCitationState.TOMBSTONED),
            _citation(
                citation_id="citation-2",
                state=ResearchDocumentCitationState.NEEDS_VERIFICATION,
            ),
        ),
    )

    assert [item.state.value for item in section.citation_refs] == [
        "tombstoned",
        "needs_verification",
    ]


def test_formatting_profile_is_pinned_to_each_immutable_document_version() -> None:
    section = ResearchDocumentSection(
        section_id="research-question",
        key="research_question",
        title="研究问题",
        content="Migration changes care work (Zhou 2024, 42).",
        status=ResearchDocumentSectionStatus.REVIEWED,
        evidence_refs=(),
        citation_refs=(_citation(),),
    )
    original = ResearchDocumentSnapshot(
        document_id=UUID(int=1),
        task_id=UUID(int=2),
        theory_plan_id=UUID(int=3),
        knowledge_release_id="release-final-1",
        revision_id=UUID(int=4),
        version=1,
        title="跨语言照护研究",
        sections=(section,),
        status=ResearchDocumentStatus.DRAFT,
        change_summary="创建文稿",
        actor="user",
        created_at=datetime(2026, 8, 31, tzinfo=UTC),
        formatting=ResearchDocumentFormatting(
            template_id="asa",
            csl_style_id="american-sociological-association",
            locale="en-US",
        ),
    )
    chinese = replace(
        original,
        revision_id=UUID(int=5),
        version=2,
        formatting=ResearchDocumentFormatting(
            template_id="chinese-social-science",
            csl_style_id="china-national-standard-gb-t-7714-2015-author-date",
            locale="zh-CN",
        ),
    )

    assert original.formatting.template_id == "asa"
    assert chinese.formatting.template_id == "chinese-social-science"
    assert original.sections == chinese.sections


def test_custom_csl_and_print_css_are_pinned_with_the_document_version() -> None:
    formatting = ResearchDocumentFormatting(
        template_id="custom",
        csl_style_id="custom-fieldwork",
        locale="zh-CN",
        custom_csl='<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0"/>',
        custom_css="body { font-family: serif; }",
    )

    assert formatting.custom_csl == '<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0"/>'
    assert formatting.custom_css == "body { font-family: serif; }"


def test_switching_template_creates_one_new_document_version() -> None:
    class Repository:
        def __init__(self) -> None:
            self.items: list[ResearchDocumentSnapshot] = []

        def add(self, snapshot):
            self.items.append(snapshot)
            return snapshot

        def latest(self, _document_id):
            return self.items[-1] if self.items else None

        def get_version(self, _document_id, version):
            return next((item for item in self.items if item.version == version), None)

        def list_versions(self, _document_id):
            return tuple(self.items)

        def list_for_task(self, task_id):
            return tuple(item for item in self.items[-1:] if item.task_id == task_id)

    ids = iter(UUID(int=value) for value in range(10, 20))
    repository = Repository()
    service = ResearchDocumentService(
        repository=repository,
        id_factory=lambda: next(ids),
        clock=lambda: datetime(2026, 8, 31, tzinfo=UTC),
    )
    section = ResearchDocumentSection(
        section_id="research-question",
        key="research_question",
        title="研究问题",
        content="迁移如何改变照护分工？",
        status=ResearchDocumentSectionStatus.REVIEWED,
        evidence_refs=(),
    )
    created = service.create(
        task_id=UUID(int=1),
        theory_plan_id=UUID(int=2),
        knowledge_release_id="release-final-1",
        title="跨语言照护研究",
        sections=(section,),
    )
    revised = service.revise(
        document_id=created.document_id,
        expected_version=created.version,
        sections=created.sections,
        change_summary="切换 ASA 模板",
        actor="user",
        formatting=ResearchDocumentFormatting(
            template_id="asa",
            csl_style_id="american-sociological-association",
            locale="en-US",
        ),
    )

    assert revised.version == 2
    assert revised.formatting.template_id == "asa"
    assert created.formatting.template_id == "chinese-social-science"


def test_api_contract_accepts_structured_citations_and_a_formatting_change() -> None:
    section = ResearchDocumentSectionContract.model_validate(
        {
            "section_id": "research-question",
            "key": "research_question",
            "title": "研究问题",
            "content": "迁移如何改变照护分工？",
            "status": "reviewed",
            "evidence_refs": [],
            "citation_refs": [
                {
                    "citation_id": "citation-1",
                    "kind": "scholarly",
                    "source_id": "literature-entry-1",
                    "source_version": "version-3",
                    "locator": {"label": "page", "value": "42-44"},
                    "state": "needs_verification",
                }
            ],
        }
    )
    request = UpdateResearchDocumentRequest(
        expected_version=3,
        sections=[section],
        change_summary="切换引用与论文格式",
        source="user_edit",
        formatting={
            "template_id": "asa",
            "csl_style_id": "american-sociological-association",
            "locale": "en-US",
        },
    )

    assert request.sections[0].citation_refs[0].source_id == "literature-entry-1"
    assert request.formatting is not None
    assert request.formatting.csl_style_id == "american-sociological-association"


def test_export_manifest_identifies_the_exact_version_and_flattens_citation_audit() -> None:
    section = ResearchDocumentSection(
        section_id="research-question",
        key="research_question",
        title="研究问题",
        content="Migration changes care work (Zhou 2024, 42).",
        status=ResearchDocumentSectionStatus.REVIEWED,
        evidence_refs=(),
        citation_refs=(
            _citation(state=ResearchDocumentCitationState.NEEDS_VERIFICATION),
        ),
    )
    document = ResearchDocumentSnapshot(
        document_id=UUID(int=1),
        task_id=UUID(int=2),
        theory_plan_id=UUID(int=3),
        knowledge_release_id="release-final-1",
        revision_id=UUID(int=4),
        version=7,
        title="跨语言照护研究",
        sections=(section,),
        status=ResearchDocumentStatus.CONFIRMED,
        change_summary="确认正式文稿",
        actor="user",
        created_at=datetime(2026, 8, 31, tzinfo=UTC),
        confirmed_at=datetime(2026, 8, 31, tzinfo=UTC),
        formatting=ResearchDocumentFormatting(
            template_id="asa",
            csl_style_id="american-sociological-association",
            locale="en-US",
        ),
    )
    plan = SimpleNamespace(
        phenomenon=SimpleNamespace(
            phenomenon_query_id=UUID(int=5),
            version=1,
            phenomenon="迁移如何改变家庭照护责任？",
            research_intent=None,
            context=None,
            content_hash="sha256:phenomenon",
            evidence_refs=(),
        ),
        knowledge_release=SimpleNamespace(
            knowledge_release_id="release-final-1",
            level=SimpleNamespace(value="final"),
            content_hash="sha256:release",
        ),
        evidence_bundle=SimpleNamespace(evidence_items=()),
        decisions=(),
        use_assignments=(),
        relations=(),
    )

    manifest = _export_manifest(
        document=document,
        plan=plan,
        match_run=SimpleNamespace(model=None, candidates=()),
        proposals=(),
        versions=(document,),
    )

    assert manifest["document_identity"] == {
        "document_id": str(document.document_id),
        "revision_id": str(document.revision_id),
        "version": 7,
    }
    assert manifest["formatting"] == {
        "template_id": "asa",
        "csl_style_id": "american-sociological-association",
        "locale": "en-US",
        "custom_csl": None,
        "custom_css": None,
    }
    assert manifest["citation_audit"] == [
        {
            "section_id": "research-question",
            "citation_id": "citation-1",
            "kind": "scholarly",
            "source_id": "literature-entry-1",
            "source_version": "version-3",
            "locator": {"label": "page", "value": "42-44"},
            "state": "needs_verification",
        }
    ]
