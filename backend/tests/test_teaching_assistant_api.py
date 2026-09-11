from uuid import uuid4

from test_research_material_api import _authenticate
from test_shared_knowledge_api import create_library, mutation


def create_activity(client, kb, kind="learning_check", **extra):
    return mutation(
        client,
        "post",
        f"/api/shared-knowledge-bases/{kb['id']}/teaching-activities",
        json={"kind": kind, "input": {"objectives": "解释课堂沉默"}, **extra},
    )


def test_activity_is_private_versioned_and_replayable(client):
    _authenticate(client)
    kb = create_library(client)
    key = str(uuid4())
    url = f"/api/shared-knowledge-bases/{kb['id']}/teaching-activities"
    body = {"kind": "learning_check", "input": {"objectives": "解释课堂沉默"}}
    first = client.post(url, json=body, headers={"Idempotency-Key": key})
    assert first.status_code == 201
    item = first.json()
    assert item["shared_with_teacher"] is False
    assert client.post(url, json=body, headers={"Idempotency-Key": key}).json()["id"] == item["id"]
    changed = mutation(
        client,
        "patch",
        "/api/teaching-activities/" + item["id"],
        json={"version": 1, "input": {"objectives": "解释课堂互动"}},
    )
    assert changed.status_code == 200
    assert changed.json()["version"] == 2
    assert (
        mutation(
            client,
            "patch",
            "/api/teaching-activities/" + item["id"],
            json={"version": 1, "shared_with_teacher": True},
        ).status_code
        == 409
    )


def test_reader_cannot_edit_settings_or_run_review_and_teacher_cannot_read_private(client):
    _authenticate(client)
    kb = create_library(client)
    teacher_cookies = dict(client.cookies)
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
    private = create_activity(client, kb).json()
    assert (
        mutation(
            client,
            "patch",
            f"/api/shared-knowledge-bases/{kb['id']}/teaching-settings",
            json={"version": 0, "objectives": "篡改", "rubric": []},
        ).status_code
        == 403
    )
    assert create_activity(client, kb, kind="lesson_plan").status_code == 403
    review = create_activity(
        client,
        kb,
        kind="assignment_review",
        shared_with_teacher=True,
        input={
            "requirements": "论述题",
            "rubric": [{"id": str(i), "title": str(i), "max_score": 10} for i in range(3)],
        },
    ).json()
    assert (
        mutation(
            client, "post", f"/api/teaching-activities/{review['id']}/run", json={"version": 1}
        ).status_code
        == 403
    )
    assert (
        mutation(
            client,
            "patch",
            f"/api/teaching-activities/{review['id']}",
            json={"version": 1, "teacher_scores": []},
        ).status_code
        == 403
    )
    client.cookies.clear()
    client.cookies.update(teacher_cookies)
    assert client.get("/api/teaching-activities/" + private["id"]).status_code == 404
    assert client.get("/api/teaching-activities/" + review["id"]).status_code == 200


def model_output(monkeypatch, payload):
    import json

    from qunxue_api.adapters.research_agent.pydantic_runner import DeterministicKnowledgeRunner
    from qunxue_api.modules.agent_conversation import AgentRunResult

    def run(self, *, prompt, conversation, tools, **kwargs):
        return AgentRunResult(
            answer=json.dumps(payload, ensure_ascii=False),
            citations=(),
            release_id=tools.release.knowledge_release_id,
            provider="deterministic-knowledge",
            model="local",
        )

    monkeypatch.setattr(DeterministicKnowledgeRunner, "run", run)


def test_learning_requires_answers_and_retains_all_stages(client, monkeypatch):
    _authenticate(client)
    kb = create_library(client)
    activity = create_activity(client, kb).json()
    url = "/api/teaching-activities/" + activity["id"]
    model_output(
        monkeypatch,
        {
            "stage": "diagnostic",
            "diagnostic_questions": [
                {"id": "q1", "prompt": "如何解释沉默？"},
                {"id": "q2", "prompt": "举一个例子。"},
            ],
        },
    )
    assert (
        mutation(client, "post", url + "/run", json={"version": activity["version"]}).status_code
        == 202
    )
    activity = client.get(url).json()
    assert activity["state"] == "ready"
    assert activity["agent_run_id"]
    assert (
        mutation(client, "post", url + "/run", json={"version": activity["version"]}).status_code
        == 422
    )
    activity = mutation(
        client,
        "patch",
        url,
        json={
            "version": activity["version"],
            "input": {
                **activity["input"],
                "diagnostic_answers": [
                    {"question_id": "q1", "answer": "害怕出错"},
                    {"question_id": "q2", "answer": "无人回答"},
                ],
            },
        },
    ).json()
    model_output(
        monkeypatch,
        {
            "stage": "practice",
            "difficulties": [{"description": "缺少机制解释", "evidence": "害怕出错"}],
            "practice": {"prompt": "如何解释线上匿名课堂仍有沉默？"},
        },
    )
    mutation(client, "post", url + "/run", json={"version": activity["version"]})
    activity = client.get(url).json()
    assert activity["result"]["stage"] == "practice"
    assert len(activity["result"]["diagnostic_questions"]) == 2
    assert (
        mutation(client, "post", url + "/run", json={"version": activity["version"]}).status_code
        == 422
    )
    activity = mutation(
        client,
        "patch",
        url,
        json={
            "version": activity["version"],
            "input": {**activity["input"], "practice_answer": "群体规范也可能影响沉默。"},
        },
    ).json()
    model_output(
        monkeypatch,
        {
            "stage": "feedback",
            "feedback": "从出错恐惧推进到群体规范解释。",
            "next_steps": ["对照具体互动记录。"],
        },
    )
    mutation(client, "post", url + "/run", json={"version": activity["version"]})
    activity = client.get(url).json()
    assert activity["result"]["stage"] == "feedback"
    assert activity["result"]["practice"]["prompt"].startswith("如何解释线上")
    assert activity["input"]["diagnostic_answers"][0]["answer"] == "害怕出错"


def test_lesson_creates_real_versioned_document(client, monkeypatch):
    _authenticate(client)
    kb = create_library(client)
    activity = create_activity(client, kb, kind="lesson_plan").json()
    model_output(monkeypatch, {"stage": "complete", "markdown": "# 课堂沉默\n\n讨论 45 分钟。"})
    url = "/api/teaching-activities/" + activity["id"]
    mutation(client, "post", url + "/run", json={"version": activity["version"]})
    activity = client.get(url).json()
    assert activity["state"] == "ready"
    assert activity["document_id"]
    document = client.get("/api/research-documents/" + activity["document_id"])
    assert document.status_code == 200
    assert "讨论 45 分钟" in document.json()["sections"][0]["content"]
    updated = mutation(
        client,
        "patch",
        url,
        json={
            "version": activity["version"],
            "document_markdown": "# 修改后\n\n案例讨论 45 分钟。",
        },
    )
    assert updated.status_code == 200
    versions = client.get(
        "/api/research-documents/" + activity["document_id"] + "/versions"
    ).json()["items"]
    assert len(versions) == 2
    assert "修改后" in versions[0]["sections"][0]["content"]
    assert "课堂沉默" in versions[1]["sections"][0]["content"]


def test_review_publication_hides_private_run_and_keeps_revision_history(client, monkeypatch):
    _authenticate(client)
    kb = create_library(client)
    teacher = dict(client.cookies)
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
    student = dict(client.cookies)
    rubric = [{"id": str(i), "title": f"维度{i}", "max_score": 10} for i in range(3)]
    activity = create_activity(
        client,
        kb,
        kind="assignment_review",
        shared_with_teacher=True,
        input={
            "requirements": "解释沉默",
            "submission_text": "沉默来自害怕出错。",
            "rubric": rubric,
        },
    ).json()
    url = "/api/teaching-activities/" + activity["id"]
    cite = {
        "material_id": None,
        "document_id": None,
        "segment_id": "submission-text",
        "title": "正文",
        "quote": "害怕出错",
    }
    suggestions = [
        {"dimension_id": str(i), "score": 6, "rationale": "还需解释机制。", "citations": [cite]}
        for i in range(3)
    ]
    model_output(
        monkeypatch,
        {"stage": "complete", "markdown": "教师内部分析", "suggested_scores": suggestions},
    )
    client.cookies.clear()
    client.cookies.update(teacher)
    mutation(client, "post", url + "/run", json={"version": activity["version"]})
    activity = client.get(url).json()
    assert activity["state"] == "ready"
    conversation_id = activity["conversation_id"]
    assert conversation_id
    assert (
        mutation(
            client, "post", url + "/publish", json={"version": activity["version"]}
        ).status_code
        == 409
    )
    client.cookies.clear()
    client.cookies.update(student)
    private = client.get(url).json()
    assert private["result"] is None and private["conversation_id"] is None
    assert client.get("/api/agent/conversations/" + conversation_id).status_code == 404
    client.cookies.clear()
    client.cookies.update(teacher)
    bad_scores = [{**s, "citations": [{**cite, "segment_id": "invented"}]} for s in suggestions]
    assert (
        mutation(
            client,
            "patch",
            url,
            json={
                "version": activity["version"],
                "teacher_scores": bad_scores,
                "teacher_feedback": "建议",
                "reviewed": True,
            },
        ).status_code
        == 422
    )
    activity = mutation(
        client,
        "patch",
        url,
        json={
            "version": activity["version"],
            "teacher_scores": [{**s, "score": 8} for s in suggestions],
            "teacher_feedback": "补充群体规范解释。",
            "reviewed": True,
        },
    ).json()
    assert activity["state"] == "reviewed"
    published = mutation(
        client, "post", url + "/publish", json={"version": activity["version"]}
    ).json()
    assert published["state"] == "published"
    assert (
        mutation(
            client, "patch", url, json={"version": published["version"], "teacher_feedback": "覆盖"}
        ).status_code
        == 409
    )
    summary = client.get(f"/api/shared-knowledge-bases/{kb['id']}/learning-summary").json()
    assert summary["sample_count"] == 1 and summary["issues"][0]["activity_ids"] == [activity["id"]]
    client.cookies.clear()
    client.cookies.update(student)
    final = client.get(url).json()
    assert final["result"]["teacher_scores"][0]["score"] == 8
    assert not final["result"]["suggested_scores"] and final["result"]["markdown"] == ""
    revised = create_activity(
        client,
        kb,
        kind="assignment_review",
        source_activity_id=activity["id"],
        shared_with_teacher=True,
        input={**activity["input"], "submission_text": "考虑群体规范。"},
    ).json()
    assert revised["source_activity_id"] == activity["id"]
    assert client.get(url).json()["result"]["teacher_feedback"] == "补充群体规范解释。"
    client.cookies.clear()
    _authenticate(client)
    assert client.get(url).status_code in {403, 404}
    assert client.get(url + "/source").status_code in {403, 404}


def test_material_grant_is_activity_scoped_and_revocation_blocks_source(client):
    from test_research_material_api import _task, _upload

    _authenticate(client)
    kb = create_library(client)
    teacher = dict(client.cookies)
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
    student = dict(client.cookies)
    task = _task(client)
    submitted = _upload(client, task).json()
    private = _upload(client, task, filename="私人.txt").json()
    activity = create_activity(
        client,
        kb,
        shared_with_teacher=True,
        input={"objectives": "学习", "material_ids": [submitted["material_id"]]},
    ).json()
    client.cookies.clear()
    client.cookies.update(teacher)
    source = client.get("/api/teaching-activities/" + activity["id"] + "/source")
    assert source.status_code == 200
    assert [i["material_id"] for i in source.json()["items"]] == [submitted["material_id"]]
    assert (
        client.get(f"/api/research-tasks/{task}/materials/{private['material_id']}").status_code
        == 404
    )
    mutation(
        client, "patch", f"/api/shared-knowledge-bases/{kb['id']}", json={"sharing_enabled": False}
    )
    assert client.get("/api/teaching-activities/" + activity["id"] + "/source").status_code in {
        403,
        404,
    }
    client.cookies.clear()
    client.cookies.update(student)
    assert client.get("/api/teaching-activities/" + activity["id"]).status_code in {403, 404}


def test_invented_model_citations_fail_without_losing_inputs(client, monkeypatch):
    _authenticate(client)
    kb = create_library(client)
    rubric = [{"id": str(i), "title": str(i), "max_score": 10} for i in range(3)]
    activity = create_activity(
        client,
        kb,
        kind="assignment_review",
        input={"requirements": "解释", "submission_text": "学生原文", "rubric": rubric},
    ).json()
    model_output(
        monkeypatch,
        {
            "stage": "complete",
            "suggested_scores": [
                {
                    "dimension_id": str(i),
                    "score": 5,
                    "rationale": "分析",
                    "citations": [{"segment_id": "fake", "title": "伪造", "quote": "不存在"}],
                }
                for i in range(3)
            ],
        },
    )
    url = "/api/teaching-activities/" + activity["id"]
    mutation(client, "post", url + "/run", json={"version": activity["version"]})
    failed = client.get(url).json()
    assert failed["state"] == "failed" and failed["result"] is None
    assert failed["input"]["submission_text"] == "学生原文"


def test_lesson_improvement_sources_require_current_activity_grant(client):
    _authenticate(client)
    kb = create_library(client)
    teacher = dict(client.cookies)
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
    student = dict(client.cookies)
    rubric = [{"id": str(i), "title": str(i), "max_score": 10} for i in range(3)]
    shared = create_activity(
        client,
        kb,
        kind="assignment_review",
        shared_with_teacher=True,
        input={"requirements": "说明", "submission_text": "授权的沉默分析", "rubric": rubric},
    ).json()
    private = create_activity(
        client,
        kb,
        kind="assignment_review",
        input={"requirements": "说明", "submission_text": "私人作业", "rubric": rubric},
    ).json()
    client.cookies.clear()
    client.cookies.update(teacher)
    assert (
        create_activity(
            client,
            kb,
            kind="lesson_plan",
            input={"objectives": "改善解释", "source_activity_ids": [private["id"]]},
        ).status_code
        == 404
    )
    lesson = create_activity(
        client,
        kb,
        kind="lesson_plan",
        input={"objectives": "改善解释", "source_activity_ids": [shared["id"]]},
    ).json()
    source_url = "/api/teaching-activities/" + lesson["id"] + "/source"
    assert client.get(source_url).json()["items"][0]["segments"][0]["text"] == "授权的沉默分析"
    client.cookies.clear()
    client.cookies.update(student)
    mutation(
        client,
        "patch",
        "/api/teaching-activities/" + shared["id"],
        json={"version": shared["version"], "shared_with_teacher": False},
    )
    client.cookies.clear()
    client.cookies.update(teacher)
    assert client.get(source_url).status_code == 404


def test_patch_null_is_rejected_and_stale_worker_cannot_finish_new_run(client):
    from uuid import UUID

    import pytest

    from qunxue_api.modules.teaching_assistant import TeachingError

    _authenticate(client)
    kb = create_library(client)
    activity = create_activity(client, kb).json()
    url = "/api/teaching-activities/" + activity["id"]
    assert (
        mutation(
            client, "patch", url, json={"version": activity["version"], "input": None}
        ).status_code
        == 422
    )
    with client.app.state.teaching_scope() as app:
        user_id = UUID(activity["owner_user_id"])
        app.start(user_id, activity["id"], {"version": 1}, "first")
        original = app.repository.get(activity["id"])
        app.fail(activity["id"], "worker interrupted", original["run_key"])
        current = app.repository.get(activity["id"])
        app.start(user_id, activity["id"], {"version": current["version"]}, "second")
        with pytest.raises(TeachingError):
            app.bind_run(user_id, activity["id"], UUID(int=1), UUID(int=2), original["run_key"])
        app.fail(activity["id"], "stale worker", original["run_key"])
        assert app.repository.get(activity["id"])["state"] == "running"


def test_reparse_keeps_the_submitted_source_version(client):
    from test_research_material_api import _task, _upload

    _authenticate(client)
    kb = create_library(client)
    task = _task(client)
    material = _upload(client, task).json()
    activity = create_activity(
        client, kb, input={"objectives": "学习", "material_ids": [material["material_id"]]}
    ).json()
    url = "/api/teaching-activities/" + activity["id"] + "/source"
    before = client.get(url).json()
    reparsed = mutation(
        client, "post", f"/api/research-tasks/{task}/materials/{material['material_id']}/reparse"
    )
    assert reparsed.status_code == 200
    assert client.get(url).json() == before


def test_course_settings_replay_and_racing_initial_version(client):
    import pytest

    from qunxue_api.modules.teaching_assistant import TeachingError

    _authenticate(client)
    kb = create_library(client)
    url = f"/api/shared-knowledge-bases/{kb['id']}/teaching-settings"
    payload = {"version": 0, "objectives": "学会论证", "rubric": []}
    key = str(uuid4())
    first = client.patch(url, json=payload, headers={"Idempotency-Key": key})
    assert first.status_code == 200 and first.json()["version"] == 1
    assert client.patch(url, json=payload, headers={"Idempotency-Key": key}).json() == first.json()
    assert mutation(client, "patch", url, json=payload).status_code == 409
    with client.app.state.teaching_scope() as app:
        value = app.repository.settings(kb["id"])
        with pytest.raises(TeachingError) as error:
            app.repository.save_settings(value, 0)
        assert error.value.status == 409


def test_teacher_can_set_review_rubric_without_expanding_student_material_scope(client):
    _authenticate(client)
    kb = create_library(client)
    teacher = dict(client.cookies)
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
    rubric = [{"id": str(i), "title": str(i), "max_score": 10} for i in range(3)]
    activity = create_activity(
        client,
        kb,
        kind="assignment_review",
        shared_with_teacher=True,
        input={"requirements": "原要求", "submission_text": "学生正文", "rubric": rubric},
    ).json()
    client.cookies.clear()
    client.cookies.update(teacher)
    url = "/api/teaching-activities/" + activity["id"]
    changed = mutation(
        client,
        "patch",
        url,
        json={
            "version": activity["version"],
            "input": {
                **activity["input"],
                "requirements": "解释具体机制",
                "rubric": [{**r, "max_score": 20} for r in rubric],
            },
        },
    )
    assert changed.status_code == 200
    assert changed.json()["input"]["rubric"][0]["max_score"] == 20
    assert (
        mutation(
            client,
            "patch",
            url,
            json={
                "version": changed.json()["version"],
                "input": {**changed.json()["input"], "submission_text": "伪造学生正文"},
            },
        ).status_code
        == 403
    )


def _published_summary_activity(client, kb, text, rationale):
    rubric = [
        {"id": "evidence", "title": "材料与论证", "max_score": 40},
        {"id": "argument", "title": "论点", "max_score": 30},
        {"id": "structure", "title": "结构", "max_score": 30},
    ]
    activity = create_activity(
        client,
        kb,
        kind="assignment_review",
        shared_with_teacher=True,
        input={"requirements": "分析课堂沉默", "submission_text": text, "rubric": rubric},
    ).json()
    cite = {
        "material_id": None,
        "document_id": None,
        "segment_id": "submission-text",
        "title": "正文",
        "quote": text,
    }
    with client.app.state.teaching_scope() as app:
        saved = app.repository.get(activity["id"])
        saved.update(
            state="published",
            version=saved["version"] + 1,
            result={
                "stage": "complete",
                "teacher_scores": [
                    {
                        "dimension_id": "evidence",
                        "score": 20,
                        "rationale": rationale,
                        "citations": [cite],
                    },
                    {
                        "dimension_id": "argument",
                        "score": None,
                        "rationale": "需要进一步判断",
                        "citations": [cite],
                    },
                    {
                        "dimension_id": "structure",
                        "score": 30,
                        "rationale": "结构完整，表达清晰",
                        "citations": [cite],
                    },
                ],
                "suggested_scores": [
                    {
                        "dimension_id": "structure",
                        "score": 10,
                        "rationale": "模型未确认意见",
                        "citations": [cite],
                    },
                ],
                "teacher_feedback": rationale,
            },
        )
        app.repository.save(saved, activity["version"])
    return activity


def test_summary_groups_confirmed_shortfalls_by_dimension_not_wording(client):
    _authenticate(client)
    kb = create_library(client)
    first = _published_summary_activity(client, kb, "害怕出错所以沉默", "缺少互动过程的证据")
    second = _published_summary_activity(
        client, kb, "群体规范维持沉默", "需要用课堂记录说明规范如何生效"
    )
    response = client.get(f"/api/shared-knowledge-bases/{kb['id']}/learning-summary")
    assert response.status_code == 200
    summary = response.json()
    assert summary["sample_count"] == 2
    assert len(summary["issues"]) == 1
    issue = summary["issues"][0]
    assert set(issue["activity_ids"]) == {first["id"], second["id"]}
    assert set(issue["evidence"]) == {"害怕出错所以沉默", "群体规范维持沉默"}
    assert "材料与论证" in issue["description"]
    assert "缺少互动过程的证据" in issue["description"]
    assert "需要用课堂记录说明规范如何生效" in issue["description"]
    assert "结构完整" not in issue["description"]
    assert "进一步判断" not in issue["description"]
    assert "模型未确认意见" not in issue["description"]


def test_summary_excludes_deleted_material_and_departed_student_without_failing(client):
    from test_research_material_api import _task, _upload

    _authenticate(client)
    kb = create_library(client)
    valid = _published_summary_activity(client, kb, "仍可查看的回答", "需要补充例证")
    task = _task(client)
    material = _upload(client, task).json()
    rubric = [{"id": str(i), "title": str(i), "max_score": 10} for i in range(3)]
    create_activity(
        client,
        kb,
        kind="assignment_review",
        shared_with_teacher=True,
        input={"requirements": "说明", "material_ids": [material["material_id"]], "rubric": rubric},
    )
    deleted = mutation(
        client, "delete", f"/api/research-tasks/{task}/materials/{material['material_id']}"
    )
    assert deleted.status_code == 204
    teacher = dict(client.cookies)
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
    _published_summary_activity(client, kb, "退出课程的回答", "退出后不应计入")
    assert (
        mutation(
            client, "delete", f"/api/shared-knowledge-base-subscriptions/{kb['id']}"
        ).status_code
        == 204
    )
    client.cookies.clear()
    client.cookies.update(teacher)
    response = client.get(f"/api/shared-knowledge-bases/{kb['id']}/learning-summary")
    assert response.status_code == 200
    summary = response.json()
    assert summary["sample_count"] == 1
    assert len(summary["issues"]) == 1
    assert summary["issues"][0]["activity_ids"] == [valid["id"]]
    assert summary["issues"][0]["evidence"] == ["仍可查看的回答"]
