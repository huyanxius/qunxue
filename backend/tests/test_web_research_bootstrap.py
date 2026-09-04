from qunxue_api.bootstrap import create_app


def test_bootstrap_passes_web_search_settings_to_the_search_adapter(
    client,
    monkeypatch,
) -> None:
    captured_search_options = []
    captured_search_clients = []

    class CapturedWebResearchClient:
        def __init__(self, **options):
            captured_search_options.append(options)

    class CapturedToolRegistry:
        def __init__(self, *, web_research, **kwargs):
            del kwargs
            captured_search_clients.append(web_research)

    monkeypatch.setattr(
        "qunxue_api.bootstrap.OpenWebResearchClient",
        CapturedWebResearchClient,
    )
    monkeypatch.setattr(
        "qunxue_api.bootstrap.ResearchDocumentToolRegistry",
        CapturedToolRegistry,
    )
    settings = client.app.state.settings.model_copy(
        update={
            "web_search_provider": "tavily",
            "web_search_allowed_domains": (),
            "web_search_timeout_seconds": 4.5,
        }
    )
    app = create_app(
        settings=settings,
        database=client.app.state.database,
        knowledge_retriever=client.app.state.knowledge_retriever,
    )

    with app.state.disciplinary_agent_scope() as application:
        application._tools_factory()

    assert len(captured_search_clients) == 1
    assert len(captured_search_options) == 1
    options = captured_search_options[0]
    assert options["search_provider"] == "tavily"
    assert options["profile"] == "sociology"
    assert options["allowed_domains"] == ()
    assert options["search_timeout_seconds"] == 4.5
    assert options["reranker"] is client.app.state.knowledge_retriever
