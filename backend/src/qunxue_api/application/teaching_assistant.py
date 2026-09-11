"""Coordinate authorized activity snapshots, persistent runs, and teaching results."""

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from qunxue_api.modules.shared_knowledge import SharedKnowledgeUnavailable
from qunxue_api.modules.teaching_assistant import (
    TeachingError,
    can_read,
    next_stage,
    projection,
    require,
    validate_citations,
    validate_input,
    validate_result,
    validate_scores,
)


def now():
    return datetime.now(UTC).isoformat()


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class TeachingAssistantApplication:
    def __init__(self, repository, courses, source_reader, documents):
        self.repository = repository
        self.courses = courses
        self.source_reader = source_reader
        self.documents = documents

    def read_raw(self, user_id, activity_id):
        activity = self.repository.get(activity_id)
        require(activity is not None, "教学记录不存在。", 404)
        kb = self.courses.require_read(user_id, UUID(activity["course_id"]))
        require(can_read(activity, user_id, kb.owner_user_id), "教学记录不存在。", 404)
        return activity, kb

    def get(self, user_id, activity_id):
        activity, kb = self.read_raw(user_id, activity_id)
        # Interrupted processes must not strand a browser on running forever.
        if activity["state"] == "running" and datetime.fromisoformat(
            activity["updated_at"]
        ) < datetime.now(UTC) - timedelta(minutes=10):
            old = activity["version"]
            activity.update(
                state="failed",
                error_message="执行中断，请重试。",
                version=old + 1,
                updated_at=now(),
            )
            self.repository.save(activity, old)
        return projection(activity, user_id, kb.owner_user_id)

    def list(self, user_id, course_id):
        kb = self.courses.require_read(user_id, course_id)
        return [
            self.get(user_id, a["id"])
            for a in sorted(
                self.repository.list(course_id), key=lambda a: a["updated_at"], reverse=True
            )
            if can_read(a, user_id, kb.owner_user_id)
        ]

    def settings(self, user_id, course_id):
        self.courses.require_read(user_id, course_id)
        return {
            k: v
            for k, v in self.repository.settings(course_id).items()
            if k not in {"receipts", "updated_by", "updated_at"}
        }

    def update_settings(self, user_id, course_id, payload, key):
        self.courses.require_manage(user_id, course_id)
        value = self.repository.settings(course_id)
        receipt = value["receipts"].get(key)
        if receipt:
            require(receipt == digest(payload), "重复请求内容不一致。", 409)
            return self.settings(user_id, course_id)
        require(value["version"] == payload["version"], "课程设置已更新，请刷新。", 409)
        require(not payload["rubric"] or 3 <= len(payload["rubric"]) <= 5, "请设置3—5项评价维度。")
        old = value["version"]
        value.update(payload, version=old + 1, updated_by=str(user_id), updated_at=now())
        value["receipts"][key] = digest(payload)
        self.repository.save_settings(value, old)
        return self.settings(user_id, course_id)

    def create(self, user_id, course_id, payload, key):
        kb = self.courses.require_read(user_id, course_id)
        teacher = str(kb.owner_user_id) == str(user_id)
        require(payload["kind"] != "lesson_plan" or teacher, "只有课程教师可以备课。", 403)
        activity_id = str(uuid5(NAMESPACE_URL, f"teaching:{user_id}:{course_id}:{key}"))
        existing = self.repository.get(activity_id)
        if existing:
            require(
                existing["receipts"].get("create:" + key) == digest(payload),
                "重复请求内容不一致。",
                409,
            )
            return self.get(user_id, activity_id)
        inputs = deepcopy(payload["input"])
        settings = self.settings(user_id, course_id)
        inputs["rubric"] = inputs.get("rubric") or settings["rubric"]
        inputs["objectives"] = inputs.get("objectives") or settings["objectives"]
        inputs["settings_version"] = settings["version"]
        validate_input(payload["kind"], inputs)
        source_id = payload.get("source_activity_id")
        if source_id:
            source, _ = self.read_raw(user_id, source_id)
            require(
                source["course_id"] == str(course_id)
                and source["kind"] == payload["kind"]
                and source["owner_user_id"] == str(user_id),
                "修订只能关联自己的同类记录。",
                403,
            )
            require(source["state"] != "running", "请等待原任务结束。", 409)
        value = dict(
            id=activity_id,
            course_id=str(course_id),
            owner_user_id=str(user_id),
            kind=payload["kind"],
            input=inputs,
            result=None,
            state="draft",
            version=1,
            shared_with_teacher=payload.get("shared_with_teacher", False),
            source_activity_id=source_id,
            agent_run_id=None,
            conversation_id=None,
            task_id=None,
            document_id=None,
            error_message=None,
            created_at=now(),
            updated_at=now(),
            executor_user_id=None,
            receipts={"create:" + key: digest(payload)},
            settings_snapshot=settings,
        )
        self.sources_for(value, user_id)
        self.repository.add(value)
        saved = self.repository.get(activity_id)
        require(
            saved["receipts"].get("create:" + key) == digest(payload), "重复请求内容不一致。", 409
        )
        return self.get(user_id, activity_id)

    def sources_for(self, activity, viewer):
        # Each read rechecks course access and the submitted owner's retained access.
        course_id = UUID(activity["course_id"])
        self.courses.require_read(viewer, course_id)
        self.courses.require_read(UUID(activity["owner_user_id"]), course_id)
        items = self.source_reader(
            UUID(activity["owner_user_id"]),
            activity["input"].get("material_ids", []),
            activity.get("source_parse_ids", {}),
        )
        activity["source_parse_ids"] = {item["material_id"]: item.pop("parse_id") for item in items}
        for document_id in activity["input"].get("course_document_ids", []):
            doc = self.courses.source(viewer, course_id, UUID(document_id), None)
            require(doc.status == "ready", "所选课程资料尚未解析完成。", 409)
            items.append(
                {
                    "material_id": None,
                    "document_id": str(doc.id),
                    "title": doc.filename,
                    "segments": [
                        {"segment_id": s["segment_id"], "text": s["text"]} for s in doc.segments
                    ],
                }
            )
        if activity["input"].get("submission_text", "").strip():
            items.append(
                {
                    "material_id": None,
                    "document_id": None,
                    "title": "提交正文",
                    "segments": [
                        {
                            "segment_id": "submission-text",
                            "text": activity["input"]["submission_text"],
                        }
                    ],
                }
            )
        if activity["input"].get("source_activity_ids"):
            require(activity["kind"] == "lesson_plan", "只有备课可以引用已授权作业。")
            self.courses.require_manage(viewer, course_id)
            for source_id in activity["input"]["source_activity_ids"]:
                submitted, _ = self.read_raw(viewer, source_id)
                require(
                    submitted["course_id"] == activity["course_id"]
                    and submitted["kind"] == "assignment_review",
                    "改进依据必须属于本课程作业。",
                )
                submitted_items = self.sources_for(submitted, viewer)["items"]
                for source_item in submitted_items:
                    if source_item["material_id"] is None and source_item["document_id"] is None:
                        for segment in source_item["segments"]:
                            segment["segment_id"] = f"activity:{source_id}:{segment['segment_id']}"
                items.extend(submitted_items)
        return {"items": items}

    def source(self, user_id, activity_id):
        activity, _ = self.read_raw(user_id, activity_id)
        return self.sources_for(activity, user_id)

    def mutation(self, activity, user_id, payload, key, operation):
        name = f"{user_id}:{operation}:{key}"
        request_hash = digest(payload)
        if name in activity["receipts"]:
            require(activity["receipts"][name] == request_hash, "重复请求内容不一致。", 409)
            return None
        require(activity["version"] == payload["version"], "记录已更新，请刷新后重试。", 409)
        activity["receipts"][name] = request_hash
        return activity["version"]

    def save(self, activity, old):
        activity.update(version=old + 1, updated_at=now())
        self.repository.save(activity, old)

    def update(self, user_id, activity_id, payload, key):
        activity, kb = self.read_raw(user_id, activity_id)
        owner = activity["owner_user_id"] == str(user_id)
        teacher = str(kb.owner_user_id) == str(user_id)
        old = self.mutation(activity, user_id, payload, key, "update")
        if old is None:
            return self.get(user_id, activity_id)
        require(activity["state"] != "running", "执行中不能修改。", 409)
        fields = set(payload) - {"version"}
        if fields & {"teacher_scores", "teacher_feedback", "reviewed"}:
            require(
                teacher and activity["kind"] == "assignment_review",
                "只有课程教师可以复核批改。",
                403,
            )
            require(
                activity["state"] in {"ready", "reviewed"},
                "请先生成建议，已发布反馈不能覆盖。",
                409,
            )
            result = activity["result"]
            if "teacher_scores" in payload:
                validate_scores(payload["teacher_scores"], activity["input"]["rubric"])
                validate_citations(
                    [c for score in payload["teacher_scores"] for c in score.get("citations", [])],
                    self.sources_for(activity, user_id),
                )
                result["teacher_scores"] = payload["teacher_scores"]
            if "teacher_feedback" in payload:
                result["teacher_feedback"] = payload["teacher_feedback"]
            activity["state"] = "ready"
            if payload.get("reviewed"):
                validate_scores(result.get("teacher_scores", []), activity["input"]["rubric"])
                require(result.get("teacher_feedback", "").strip(), "请确认给学生的反馈。")
                activity["state"] = "reviewed"
        if "shared_with_teacher" in payload:
            require(owner, "只有记录本人可以调整分享。", 403)
            activity["shared_with_teacher"] = payload["shared_with_teacher"]
        if "input" in payload:
            require(
                owner or teacher and activity["kind"] == "assignment_review",
                "只有记录本人或负责批改的课程教师可以修改输入。",
                403,
            )
            if not owner:
                require(
                    all(
                        payload["input"].get(field) == value
                        for field, value in activity["input"].items()
                        if field not in {"requirements", "rubric"}
                    ),
                    "教师只能修改作业要求与评价标准，不能改动学生提交范围。",
                    403,
                )
            require(
                activity["state"] in {"draft", "failed"}
                or activity["kind"] == "learning_check"
                and activity["state"] == "ready",
                "已有结果请创建修订，保留原记录。",
                409,
            )
            new_input = payload["input"]
            validate_input(activity["kind"], new_input)
            if activity.get("result"):
                for name in set(activity["input"]) - {"diagnostic_answers", "practice_answer"}:
                    require(
                        new_input.get(name) == activity["input"].get(name),
                        "诊断后只能补充当前阶段回答。",
                        409,
                    )
                stage = activity["result"]["stage"]
                if stage != "diagnostic":
                    require(
                        new_input["diagnostic_answers"] == activity["input"]["diagnostic_answers"],
                        "已分析的诊断回答不能覆盖。",
                        409,
                    )
                if stage == "feedback":
                    require(new_input == activity["input"], "学习任务已完成，请创建新记录。", 409)
            activity["input"] = new_input
            self.sources_for(activity, user_id)
        if fields & {"document_markdown", "revision_instruction", "selected_text"}:
            require(
                owner and activity["kind"] == "lesson_plan" and activity["state"] == "ready",
                "教案尚不可编辑。",
                409,
            )
            if "document_markdown" in payload:
                require(payload["document_markdown"].strip(), "教案正文不能为空。")
                activity["result"]["markdown"] = payload["document_markdown"]
                activity["document_id"] = self.documents.save(
                    activity, payload["document_markdown"]
                )
            activity["revision_instruction"] = payload.get("revision_instruction", "")
            activity["selected_text"] = payload.get("selected_text", "")
        self.save(activity, old)
        return self.get(user_id, activity_id)

    def start(self, user_id, activity_id, payload, key):
        activity, kb = self.read_raw(user_id, activity_id)
        teacher = str(kb.owner_user_id) == str(user_id)
        require(
            teacher
            if activity["kind"] in {"lesson_plan", "assignment_review"}
            else activity["owner_user_id"] == str(user_id),
            "你无权运行此任务。",
            403,
        )
        old = self.mutation(activity, user_id, payload, key, "run")
        if old is None:
            return self.get(user_id, activity_id), False
        require(activity["state"] in {"draft", "failed", "ready"}, "当前任务不能运行。", 409)
        require(
            activity["state"] != "ready"
            or activity["kind"] == "learning_check"
            or activity["kind"] == "lesson_plan"
            and activity.get("revision_instruction"),
            "请创建修订，保留已有结果。",
            409,
        )
        stage = next_stage(activity)
        self.sources_for(activity, user_id)
        if activity["kind"] == "assignment_review":
            require(
                activity["input"]["material_ids"]
                or activity["input"].get("submission_text", "").strip(),
                "请先上传作业或填写正文。",
            )
        activity.update(
            state="running",
            error_message=None,
            executor_user_id=str(user_id),
            run_key=f"teaching:{activity_id}:{key}",
        )
        self.save(activity, old)
        return self.get(user_id, activity_id), stage

    def bind_run(self, user_id, activity_id, run_id, conversation_id, expected_key=None):
        activity, _ = self.read_raw(user_id, activity_id)
        require(
            activity["state"] == "running"
            and (expected_key is None or activity["run_key"] == expected_key),
            "执行已取消。",
            409,
        )
        old = activity["version"]
        activity.update(agent_run_id=str(run_id), conversation_id=str(conversation_id))
        self.save(activity, old)

    def finish(self, user_id, activity_id, result, stage, task_id=None, expected_key=None):
        activity, _ = self.read_raw(user_id, activity_id)
        require(
            activity["state"] == "running"
            and (expected_key is None or activity["run_key"] == expected_key),
            "执行已结束。",
            409,
        )
        result = validate_result(activity, result, self.sources_for(activity, user_id), stage)
        if stage in {"practice", "feedback"}:
            previous = activity.get("result") or {}
            for field in ("diagnostic_questions", "recommendations", "difficulties", "practice"):
                if not result.get(field):
                    result[field] = previous.get(field, [] if field != "practice" else None)
        old = activity["version"]
        activity.update(
            state="ready",
            result=result,
            task_id=activity["task_id"] or (str(task_id) if task_id else None),
            revision_instruction="",
            selected_text="",
        )
        if activity["kind"] == "lesson_plan":
            activity["document_id"] = self.documents.save(activity, result["markdown"])
        self.save(activity, old)

    def fail(self, activity_id, message, expected_key=None):
        activity = self.repository.get(activity_id)
        if (
            activity
            and activity["state"] == "running"
            and (expected_key is None or activity["run_key"] == expected_key)
        ):
            old = activity["version"]
            activity.update(state="failed", error_message=message)
            self.save(activity, old)

    def publish(self, user_id, activity_id, payload, key):
        activity, kb = self.read_raw(user_id, activity_id)
        require(
            str(kb.owner_user_id) == str(user_id) and activity["kind"] == "assignment_review",
            "只有课程教师可以发布。",
            403,
        )
        old = self.mutation(activity, user_id, payload, key, "publish")
        if old is None:
            return self.get(user_id, activity_id)
        require(activity["state"] == "reviewed", "请先完成教师复核。", 409)
        self.sources_for(activity, user_id)
        activity["state"] = "published"
        self.save(activity, old)
        return self.get(user_id, activity_id)

    def summary(self, user_id, course_id):
        self.courses.require_manage(user_id, course_id)
        activities = [
            a
            for a in self.list(user_id, course_id)
            if a["kind"] == "assignment_review" and a["shared_with_teacher"]
        ]
        issues = {}
        comments = {}
        available = []
        for activity in activities:
            scores = (activity["result"] or {}).get("teacher_scores", [])
            try:
                sources = self.source(user_id, activity["id"])
                validate_citations(
                    [cite for score in scores for cite in score.get("citations", [])], sources
                )
            except SharedKnowledgeUnavailable:
                continue
            except TeachingError as error:
                if error.status not in {403, 404, 409, 422}:
                    raise
                continue
            available.append(activity)
            if activity["state"] != "published":
                continue
            rubric = {dimension["id"]: dimension for dimension in activity["input"]["rubric"]}
            for score in scores:
                dimension = rubric.get(score["dimension_id"])
                value = score.get("score")
                if (
                    dimension is None
                    or value is None
                    or not 0 <= value < dimension["max_score"]
                    or not score.get("citations")
                ):
                    continue
                key = dimension["id"]
                issue = issues.setdefault(
                    key, {"description": dimension["title"], "activity_ids": [], "evidence": []}
                )
                details = comments.setdefault(key, [])
                rationale = score["rationale"].strip()
                if rationale and rationale not in details:
                    details.append(rationale)
                if activity["id"] not in issue["activity_ids"]:
                    issue["activity_ids"].append(activity["id"])
                issue["evidence"] = list(
                    dict.fromkeys(
                        [*issue["evidence"], *(cite["quote"] for cite in score["citations"])]
                    )
                )
        for key, issue in issues.items():
            if comments[key]:
                issue["description"] += "：" + "；".join(comments[key])
        return {
            "sample_count": len(available),
            "issues": list(issues.values()),
            "updated_at": max((a["updated_at"] for a in available), default=None),
        }
