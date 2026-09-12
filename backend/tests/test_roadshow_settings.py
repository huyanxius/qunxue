import json
from types import SimpleNamespace
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from qunxue_api.api.dependencies import get_current_session
from qunxue_api.api.routes.roadshow import router


def test_settings_only_configured_user_can_read_and_write(tmp_path):
    path = tmp_path / "roadshow.json"
    path.write_text(
        json.dumps(
            {
                "user_id": str(UUID(int=1)),
                "cases": [
                    {
                        "title": "食堂",
                        "keywords": ["食堂"],
                        "question": "切入点？",
                        "options": ["空间"],
                        "steps": ["检索"],
                        "answer": "# 报告\n\n## 空间\n内容",
                    }
                ],
            }
        )
    )
    app = FastAPI()
    app.state.roadshow_path = path
    app.include_router(router)
    current = SimpleNamespace(user=SimpleNamespace(user_id=UUID(int=2)))
    app.dependency_overrides[get_current_session] = lambda: current
    with TestClient(app) as client:
        assert client.get("/api/roadshow").status_code == 404
        assert client.put("/api/roadshow", json={"cases": []}).status_code in (404, 422)
        current.user.user_id = UUID(int=1)
        body = client.get("/api/roadshow").json()
        assert "user_id" not in body
        body["cases"][0]["answer"] = "修改后的回答"
        assert client.put("/api/roadshow", json=body).status_code == 200
        saved = json.loads(path.read_text())
        assert saved["user_id"] == str(UUID(int=1))
        assert saved["cases"][0]["answer"] == "修改后的回答"
        assert client.post("/api/roadshow/reset").json()["cases"][0]["answer"].startswith("# 报告")
