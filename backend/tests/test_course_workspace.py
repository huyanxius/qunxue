from test_research_material_api import _authenticate
from test_shared_knowledge_api import create_library, mutation, upload


def test_course_identity_is_saved_per_account(client):
    _authenticate(client)
    response = client.get("/api/course-profile")
    assert response.status_code == 200
    assert response.json()["role"] is None
    assert (
        mutation(client, "patch", "/api/course-profile", json={"role": "teacher"}).json()["role"]
        == "teacher"
    )
    assert client.get("/api/course-profile").json()["role"] == "teacher"
    client.cookies.clear()
    _authenticate(client)
    assert client.get("/api/course-profile").json()["role"] is None


def test_uploaded_document_is_organized_with_original_source_anchors(client):
    _authenticate(client)
    kb = create_library(client)
    doc = upload(client, kb["id"])
    assert doc.get("knowledge_status") == "queued"
    source = client.get(
        f"/api/shared-knowledge-bases/{kb['id']}/documents/{doc['id']}/source"
    ).json()
    segment_id = source["segments"][0]["segment_id"]
    client.app.state.course_organization_worker.generate = lambda document: {
        "summary": "访谈记录的课堂规范。",
        "topics": [
            {
                "title": "记录标识",
                "summary": "访谈记录统一使用 QX-A17。",
                "segment_ids": [segment_id],
            }
        ],
    }
    assert client.app.state.course_organization_worker.run_once()
    result = client.get(f"/api/shared-knowledge-bases/{kb['id']}").json()["documents"][0]
    assert result["knowledge_status"] == "ready"
    assert result["knowledge"]["topics"][0]["segment_ids"] == [segment_id]
    assert result["knowledge"]["summary"] == "访谈记录的课堂规范。"
    assert (
        client.get(f"/api/shared-knowledge-bases/{kb['id']}/documents/{doc['id']}/source").json()[
            "segments"
        ]
        == source["segments"]
    )


def test_organization_rejects_invented_sources_and_can_retry(client):
    _authenticate(client)
    kb = create_library(client)
    doc = upload(client, kb["id"])
    assert doc.get("knowledge_status") == "queued"
    client.app.state.course_organization_worker.generate = lambda document: {
        "summary": "无依据",
        "topics": [{"title": "伪造", "summary": "不能保存", "segment_ids": ["foreign-id"]}],
    }
    client.app.state.course_organization_worker.run_once()
    result = client.get(f"/api/shared-knowledge-bases/{kb['id']}").json()["documents"][0]
    assert result["knowledge_status"] == "failed"
    assert result["knowledge"] is None
    retried = mutation(
        client, "post", f"/api/shared-knowledge-bases/{kb['id']}/documents/{doc['id']}/organize"
    )
    assert retried.status_code == 202
    assert retried.json()["knowledge_status"] == "queued"


def test_course_index_is_built_once_and_reused(client):
    _authenticate(client)
    kb = create_library(client)
    doc = upload(client, kb["id"])
    worker = client.app.state.course_organization_worker
    worker.generate = lambda document: {
        "summary": "课程",
        "topics": [
            {
                "title": "记录",
                "summary": "记录规范",
                "segment_ids": [document.segments[0]["segment_id"]],
            }
        ],
    }

    class Embedder:
        def embed_documents(self, texts):
            return [[1.0, 0.0] for _ in texts]

    worker.embedder = Embedder()
    worker.embedding_model = "test-embedding"
    worker.run_once()
    worker.run_once()
    result = client.get(f"/api/shared-knowledge-bases/{kb['id']}").json()["documents"][0]
    assert result["index_status"] == "ready"
    with client.app.state.shared_knowledge_scope() as app:
        from qunxue_api.adapters.sqlite.shared_knowledge import SharedDocumentRow

        row = app.repository.session.get(SharedDocumentRow, doc["id"])
        assert list(row.vectors["test-embedding"].values()) == [[1.0, 0.0]]
    assert worker.run_once() is False


def test_course_guide_dismissal_is_saved_with_the_role(client):
    _authenticate(client)
    assert client.get("/api/course-profile").json()["guide_dismissed"] is False
    result = mutation(
        client, "patch", "/api/course-profile", json={"role": "student", "guide_dismissed": True}
    )
    assert result.status_code == 200
    assert client.get("/api/course-profile").json() == {"role": "student", "guide_dismissed": True}


def test_index_retry_keeps_finished_batches_and_ignores_detached_documents(client):
    from qunxue_api.adapters.sqlite.shared_knowledge import SharedDocumentRow

    _authenticate(client)
    kb = create_library(client)
    doc = upload(client, kb["id"])
    worker = client.app.state.course_organization_worker
    with client.app.state.shared_knowledge_scope() as app:
        row = app.repository.session.get(SharedDocumentRow, doc["id"])
        original = row.segments[0]
        row.segments = [
            {**original, "segment_id": f"part-{i}", "text": f"课程内容 {i}"} for i in range(18)
        ]
        row.knowledge_status = "ready"
        app.repository.commit()
    batches = []

    class Embedder:
        fail = True

        def embed_documents(self, texts):
            batches.append(list(texts))
            if len(texts) == 2 and self.fail:
                raise RuntimeError("provider temporarily unavailable")
            return [[1.0, 0.0] for text in texts]

    worker.embedder, worker.embedding_model = Embedder(), "test-embedding"
    worker.run_once()
    assert (
        client.get(f"/api/shared-knowledge-bases/{kb['id']}").json()["documents"][0]["index_status"]
        == "failed"
    )
    worker.embedder.fail = False
    mutation(
        client, "post", f"/api/shared-knowledge-bases/{kb['id']}/documents/{doc['id']}/organize"
    )
    worker.run_once()
    assert [len(batch) for batch in batches] == [16, 2, 2]
    result = client.get(f"/api/shared-knowledge-bases/{kb['id']}").json()["documents"][0]
    assert result["index_status"] == "ready"
    detached = upload(client, kb["id"], text="这份资料不应发送给模型")
    mutation(client, "delete", f"/api/shared-knowledge-bases/{kb['id']}/documents/{detached['id']}")
    assert worker.run_once() is False


def test_index_rejects_inconsistent_vector_dimensions(client):
    from qunxue_api.adapters.sqlite.shared_knowledge import SharedDocumentRow

    _authenticate(client)
    kb = create_library(client)
    doc = upload(client, kb["id"])
    with client.app.state.shared_knowledge_scope() as app:
        row = app.repository.session.get(SharedDocumentRow, doc["id"])
        row.segments = [row.segments[0], {**row.segments[0], "segment_id": "second"}]
        row.knowledge_status = "ready"
        app.repository.commit()

    class Embedder:
        def embed_documents(self, texts):
            return [[1.0, 0.0], [1.0]]

    worker = client.app.state.course_organization_worker
    worker.embedder, worker.embedding_model = Embedder(), "invalid-provider"
    worker.run_once()
    assert (
        client.get(f"/api/shared-knowledge-bases/{kb['id']}").json()["documents"][0]["index_status"]
        == "failed"
    )
