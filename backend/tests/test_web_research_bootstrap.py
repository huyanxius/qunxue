from qunxue_api.bootstrap import create_app


def test_bootstrap_configures_web_research_and_the_page_read_switch(
    client,
    monkeypatch,
) -> None:
    captured_search_options = []
    captured_search_clients = []
    captured_read_flags = []

    class CapturedWebResearchClient:
        def __init__(self, **options):
            captured_search_options.append(options)

    class CapturedToolRegistry:
        def __init__(self, *, web_research, web_read_enabled, **kwargs):
            del kwargs
            captured_search_clients.append(web_research)
            captured_read_flags.append(web_read_enabled)

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
            "web_read_enabled": False,
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
    assert captured_read_flags == [False]
    assert len(captured_search_options) == 1
    options = captured_search_options[0]
    assert options["search_provider"] == "tavily"
    assert options["profile"] == "sociology"
    assert options["allowed_domains"] == ()
    assert options["search_timeout_seconds"] == 4.5
    assert options["reranker"] is client.app.state.knowledge_retriever
