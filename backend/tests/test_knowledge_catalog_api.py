from fastapi.testclient import TestClient


def test_current_knowledge_release_is_a_stable_markdown_preview(client: TestClient) -> None:
    first = client.get("/api/knowledge/releases/current")
    second = client.get("/api/knowledge/releases/current")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["knowledge_release_id"].startswith("knowledge-preview-")
    assert first.json()["level"] == "preview"
    assert first.json()["content_hash"].startswith("sha256:")
