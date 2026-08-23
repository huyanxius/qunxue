from types import SimpleNamespace

from qunxue_api.bootstrap import create_app


def test_bootstrap_injects_one_shared_retriever_into_m4_and_agent_tools(
    client,
    monkeypatch,
) -> None:
    retriever = SimpleNamespace(name="shared-release-bound-retriever")
    evidence_retrievers = []
    tool_retrievers = []

    class CapturedEvidenceSource:
        def __init__(self, catalog, *, retriever):
            del catalog
            evidence_retrievers.append(retriever)

    class CapturedToolRegistry:
        def __init__(self, *, retriever, **kwargs):
            del kwargs
            tool_retrievers.append(retriever)

    monkeypatch.setattr(
        "qunxue_api.bootstrap.CatalogTheoryEvidenceSource",
        CapturedEvidenceSource,
    )
    monkeypatch.setattr(
        "qunxue_api.bootstrap.ResearchDocumentToolRegistry",
        CapturedToolRegistry,
    )

    app = create_app(
        settings=client.app.state.settings,
        database=client.app.state.database,
        knowledge_retriever=retriever,
    )

    with app.state.theory_matching_application_scope():
        pass
    with app.state.disciplinary_agent_scope() as application:
        application._tools_factory()

    assert app.state.knowledge_retriever is retriever
    assert evidence_retrievers == [retriever, retriever]
    assert tool_retrievers == [retriever]
