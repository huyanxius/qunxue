"""Course sharing must never broaden personal-material or conversation access."""

from uuid import uuid4

from test_research_material_api import _authenticate


def mutation(client, method, path, **kwargs):
    return getattr(client, method)(path, headers={"Idempotency-Key": str(uuid4())}, **kwargs)


def create_library(client):
    response = mutation(
        client,
        "post",
        "/api/shared-knowledge-bases",
        json={
            "name": "社会调查方法",
            "description": "课堂参考资料",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, kb, text="课堂记录统一使用 QX-A17 标记。", filename="课堂.txt"):
    response = mutation(
        client,
        "post",
        f"/api/shared-knowledge-bases/{kb}/documents",
        files={"file": (filename, text.encode(), "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_teacher_upload_uses_source_blocks_without_creating_research(client):
    _authenticate(client)
    kb = create_library(client)
    assert kb["sharing_enabled"] is False
    doc = upload(client, kb["id"])
    assert doc["status"] == "ready"
    source = client.get(f"/api/shared-knowledge-bases/{kb['id']}/documents/{doc['id']}/source")
    assert source.status_code == 200
    assert source.json()["segments"][0]["text"] == "课堂记录统一使用 QX-A17 标记。"
    assert source.json()["segments"][0]["locator"]["paragraph"] == 1
    assert client.get("/api/agent/conversations").json()["items"] == []


def test_reader_requires_subscription_and_open_sharing_and_cannot_manage(client):
    _authenticate(client)
    owner_cookies = dict(client.cookies)
    kb = create_library(client)
    doc = upload(client, kb["id"])
    path = f"/api/shared-knowledge-bases/{kb['id']}"
    source_path = f"{path}/documents/{doc['id']}/source"
    mutation(client, "patch", path, json={"sharing_enabled": True})
    client.cookies.clear()
    _authenticate(client)
    assert client.get(path).status_code == 404
    assert client.get(source_path).status_code == 404
    joined = mutation(
        client,
        "post",
        "/api/shared-knowledge-base-subscriptions",
        json={"share_token": kb["share_token"]},
    )
    assert joined.status_code == 200
    assert joined.json()["added"] is True
    assert (
        mutation(
            client,
            "post",
            "/api/shared-knowledge-base-subscriptions",
            json={"share_token": kb["share_token"]},
        ).json()["added"]
        is False
    )
    detail = client.get(path).json()
    assert detail["viewer_access"] == "reader"
    assert not detail.get("share_token")
    assert client.get(source_path).status_code == 200
    assert mutation(client, "patch", path, json={"name": "篡改"}).status_code == 403
    assert mutation(client, "delete", f"{path}/documents/{doc['id']}").status_code == 403
    reader_cookies = dict(client.cookies)
    client.cookies.clear()
    client.cookies.update(owner_cookies)
    assert mutation(client, "patch", path, json={"sharing_enabled": False}).status_code == 200
    client.cookies.clear()
    client.cookies.update(reader_cookies)
    assert client.get(source_path).status_code == 404
    assert client.get(path).status_code == 404
    assert (
        client.get("/api/shared-knowledge-bases").json()["items"][0]["viewer_access"]
        == "unavailable"
    )
    client.cookies.clear()
    client.cookies.update(owner_cookies)
    mutation(client, "patch", path, json={"sharing_enabled": True})
    client.cookies.clear()
    client.cookies.update(reader_cookies)
    assert client.get(source_path).status_code == 200
    mutation(client, "delete", f"/api/shared-knowledge-base-subscriptions/{kb['id']}")
    assert client.get(source_path).status_code == 404


def test_source_rejects_cross_library_and_cross_document_segment_ids(client):
    _authenticate(client)
    a, b = create_library(client), create_library(client)
    doc_a, doc_b = upload(client, a["id"]), upload(client, b["id"], "不可混入的 B 资料")
    path_a = f"/api/shared-knowledge-bases/{a['id']}/documents/{doc_a['id']}/source"
    source_b = client.get(
        f"/api/shared-knowledge-bases/{b['id']}/documents/{doc_b['id']}/source"
    ).json()
    assert (
        client.get(
            f"/api/shared-knowledge-bases/{a['id']}/documents/{doc_b['id']}/source"
        ).status_code
        == 404
    )
    assert (
        client.get(path_a, params={"segment_id": source_b["segments"][0]["segment_id"]}).status_code
        == 404
    )
    mutation(client, "delete", f"/api/shared-knowledge-bases/{a['id']}/documents/{doc_a['id']}")
    assert client.get(path_a).status_code == 404


def test_failed_parse_is_not_exposed_to_reader(client):
    _authenticate(client)
    kb = create_library(client)
    failed = upload(client, kb["id"], "")
    assert failed["status"] == "failed"
    assert failed["error_message"]
    mutation(
        client, "patch", f"/api/shared-knowledge-bases/{kb['id']}", json={"sharing_enabled": True}
    )
    client.cookies.clear()
    _authenticate(client)
    mutation(
        client,
        "post",
        "/api/shared-knowledge-base-subscriptions",
        json={"share_token": kb["share_token"]},
    )
    assert client.get(f"/api/shared-knowledge-bases/{kb['id']}").json()["documents"] == []


def test_create_is_idempotent_and_mutations_require_key(client):
    _authenticate(client)
    body = {"name": "同一门课"}
    assert client.post("/api/shared-knowledge-bases", json=body).status_code == 422
    headers = {"Idempotency-Key": str(uuid4())}
    a = client.post("/api/shared-knowledge-bases", json=body, headers=headers)
    b = client.post("/api/shared-knowledge-bases", json=body, headers=headers)
    assert a.status_code == b.status_code == 201
    assert a.json()["id"] == b.json()["id"]
    assert len(client.get("/api/shared-knowledge-bases").json()["items"]) == 1


def test_deleted_library_keeps_reader_unavailable_marker(client):
    _authenticate(client)
    owner_cookies = dict(client.cookies)
    kb = create_library(client)
    mutation(
        client, "patch", f"/api/shared-knowledge-bases/{kb['id']}", json={"sharing_enabled": True}
    )
    client.cookies.clear()
    _authenticate(client)
    mutation(
        client,
        "post",
        "/api/shared-knowledge-base-subscriptions",
        json={"share_token": kb["share_token"]},
    )
    reader_cookies = dict(client.cookies)
    client.cookies.clear()
    client.cookies.update(owner_cookies)
    assert mutation(client, "delete", f"/api/shared-knowledge-bases/{kb['id']}").status_code == 204
    client.cookies.clear()
    client.cookies.update(reader_cookies)
    item = client.get("/api/shared-knowledge-bases").json()["items"][0]
    assert item["id"] == kb["id"]
    assert item["viewer_access"] == "unavailable"


def test_pptx_reports_unreadable_slide_numbers(client):
    from io import BytesIO
    from zipfile import ZipFile

    from test_shared_knowledge_pptx import pptx_fixture

    _authenticate(client)
    kb = create_library(client)
    data = BytesIO()
    with ZipFile(BytesIO(pptx_fixture())) as source, ZipFile(data, "w") as target:
        for name in source.namelist():
            content = source.read(name)
            if name == "ppt/slides/slide1.xml":
                content = b'<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree/></p:cSld></p:sld>'
            target.writestr(name, content)
    result = mutation(
        client,
        "post",
        f"/api/shared-knowledge-bases/{kb['id']}/documents",
        files={"file": ("课堂.pptx", data.getvalue(), "application/octet-stream")},
    )
    assert result.status_code == 201
    assert result.json()["status"] == "ready"
    assert "2" in result.json()["warnings"][0]


def test_upload_retry_does_not_duplicate_or_reattach_removed_file(client):
    _authenticate(client)
    kb = create_library(client)
    path = f"/api/shared-knowledge-bases/{kb['id']}/documents"
    headers = {"Idempotency-Key": str(uuid4())}
    files = {"file": ("课件.txt", b"original", "text/plain")}
    first = client.post(path, headers=headers, files=files)
    retry = client.post(path, headers=headers, files=files)
    assert first.json()["id"] == retry.json()["id"]
    conflict = client.post(
        path, headers=headers, files={"file": ("课件.txt", b"changed", "text/plain")}
    )
    assert conflict.status_code == 422
    mutation(client, "delete", f"{path}/{first.json()['id']}")
    assert client.post(path, headers=headers, files=files).status_code == 201
    assert client.get(f"/api/shared-knowledge-bases/{kb['id']}").json()["documents"] == []


def test_concurrent_upload_retry_has_one_document(client):
    from concurrent.futures import ThreadPoolExecutor

    _authenticate(client)
    kb = create_library(client)
    path = f"/api/shared-knowledge-bases/{kb['id']}/documents"
    headers = {"Idempotency-Key": str(uuid4())}

    def send():
        return client.post(
            path, headers=headers, files={"file": ("课件.txt", b"concurrent", "text/plain")}
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: send(), range(2)))
    assert all(response.status_code == 201 for response in responses)
    assert responses[0].json()["id"] == responses[1].json()["id"]
    assert len(client.get(f"/api/shared-knowledge-bases/{kb['id']}").json()["documents"]) == 1


def test_upload_rejects_unsupported_or_mismatched_formats(client):
    _authenticate(client)
    kb = create_library(client)
    for filename, mime in [("答案.exe", "application/octet-stream"), ("课件.pptx", "text/plain")]:
        response = mutation(
            client,
            "post",
            f"/api/shared-knowledge-bases/{kb['id']}/documents",
            files={"file": (filename, b"unsupported", mime)},
        )
        assert response.status_code == 422


def test_concurrent_create_retry_has_one_library(client):
    from concurrent.futures import ThreadPoolExecutor

    _authenticate(client)
    headers = {"Idempotency-Key": str(uuid4())}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(
                    "/api/shared-knowledge-bases", headers=headers, json={"name": "同一请求"}
                ),
                range(2),
            )
        )
    assert all(response.status_code == 201 for response in responses)
    assert responses[0].json()["id"] == responses[1].json()["id"]
