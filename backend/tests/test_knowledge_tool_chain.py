from types import SimpleNamespace

from qunxue_api.adapters.research_agent.catalog_tools import KnowledgeToolRegistry


def test_read_knowledge_entry_returns_source_ids_for_the_next_tool_call() -> None:
    release = SimpleNamespace(knowledge_release_id="release-a")
    detail = SimpleNamespace(
        summary=SimpleNamespace(
            knowledge_id="D1:C001",
            title="符号互动论",
            eligibility=SimpleNamespace(rag_eligible=True),
        ),
        aliases=("互动论",),
        content="互动中的意义建构。",
        sources=(
            SimpleNamespace(source_id="source:a"),
            SimpleNamespace(source_id="source:b"),
        ),
    )

    class Catalog:
        def current_release(self, *, purpose):
            del purpose
            return release

        def get_entry(self, *, knowledge_id, release_id):
            assert knowledge_id == "D1:C001"
            assert release_id == "release-a"
            return detail

    result = KnowledgeToolRegistry(Catalog()).read_knowledge_entry("D1:C001")

    assert result["source_ids"] == ["source:a", "source:b"]


def test_agent_registry_pins_matching_release_for_research_provenance() -> None:
    release = SimpleNamespace(knowledge_release_id="release-final")
    purposes = []

    class Catalog:
        def current_release(self, *, purpose):
            purposes.append(purpose)
            return release

    KnowledgeToolRegistry(Catalog())

    assert purposes == ["match"]
