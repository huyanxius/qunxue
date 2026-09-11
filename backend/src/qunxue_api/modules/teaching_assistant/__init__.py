"""Classroom activity rules independent of persistence and HTTP."""

from copy import deepcopy


class TeachingError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def require(condition, message, status=422):
    if not condition:
        raise TeachingError(message, status)


def can_read(activity, user_id, teacher_id):
    return activity["owner_user_id"] == str(user_id) or (
        str(user_id) == str(teacher_id) and activity["shared_with_teacher"]
    )


def projection(activity, user_id, teacher_id):
    value = deepcopy(activity)
    # Private Agent traces never become a side channel for a shared activity.
    if str(user_id) != value.get("executor_user_id"):
        for key in ("agent_run_id", "conversation_id", "task_id", "document_id"):
            value[key] = None
    if value["kind"] == "assignment_review" and str(user_id) != str(teacher_id):
        value["error_message"] = None
        if value["state"] != "published":
            value["result"] = None
        elif value["result"]:
            result = value["result"]
            value["result"] = {
                "stage": "complete",
                "teacher_scores": result.get("teacher_scores", []),
                "teacher_feedback": result.get("teacher_feedback", ""),
                "citations": result.get("citations", []),
            }
    return {
        key: val
        for key, val in value.items()
        if key
        not in {
            "executor_user_id",
            "receipts",
            "run_key",
            "revision_instruction",
            "selected_text",
            "settings_snapshot",
            "source_parse_ids",
        }
    }


def validate_input(kind, inputs):
    if kind in {"lesson_plan", "learning_check"}:
        require(inputs.get("objectives", "").strip(), "请填写目标。")
    if kind == "assignment_review":
        require(inputs.get("requirements", "").strip(), "请填写作业要求。")
        rubric = inputs.get("rubric", [])
        require(3 <= len(rubric) <= 5, "请设置3—5项评价维度。")
        require(len({item["id"] for item in rubric}) == len(rubric), "评价维度不能重复。")


def next_stage(activity):
    if activity["kind"] != "learning_check":
        return "complete"
    old = activity.get("result") or {}
    stage = old.get("stage")
    if not stage:
        return "diagnostic"
    if stage == "diagnostic":
        questions = {q["id"] for q in old.get("diagnostic_questions", [])}
        answers = activity["input"].get("diagnostic_answers", [])
        require(
            questions
            and {a["question_id"] for a in answers} == questions
            and all(a["answer"].strip() for a in answers)
            and len(answers) == len(questions),
            "请先回答全部诊断问题。",
        )
        return "practice"
    if stage == "practice":
        require(activity["input"].get("practice_answer", "").strip(), "请先完成练习。")
        return "feedback"
    raise TeachingError("本次学习已完成，请创建新的学习任务。", 409)


def validate_scores(scores, rubric):
    dimensions = {item["id"]: item["max_score"] for item in rubric}
    require(
        len(scores) == len(dimensions) and {s["dimension_id"] for s in scores} == set(dimensions),
        "请逐项确认评价维度。",
    )
    for score in scores:
        require(
            score["score"] is None or 0 <= score["score"] <= dimensions[score["dimension_id"]],
            "分数超出评价维度满分。",
        )


def validate_result(activity, result, sources, stage):
    require(result["stage"] == stage, "模型返回的学习阶段不匹配。")
    citations = list(result.get("citations", []))
    for score in result.get("suggested_scores", []):
        citations.extend(score.get("citations", []))
        if not score.get("citations"):
            score["score"] = None
            score["rationale"] = "需要教师判断。" + score.get("rationale", "")
    citations.extend(r["source"] for r in result.get("recommendations", []))
    validate_citations(citations, sources)
    result["teacher_scores"] = []
    result["teacher_feedback"] = ""
    if activity["kind"] == "assignment_review":
        validate_scores(result.get("suggested_scores", []), activity["input"]["rubric"])
    if stage == "diagnostic":
        questions = result.get("diagnostic_questions", [])
        require(
            2 <= len(questions) <= 3 and len({q["id"] for q in questions}) == len(questions),
            "模型需要返回2—3个不同的诊断问题。",
        )
        require(
            not result.get("difficulties") and not result.get("feedback"),
            "未作答不能判断掌握情况。",
        )
    if stage == "practice":
        require(result.get("practice") and result.get("difficulties"), "模型未返回困难依据或练习。")
        require(len(result.get("recommendations", [])) <= 5, "推荐资料不得超过5项。")
        answers = [a["answer"] for a in activity["input"]["diagnostic_answers"]]
        require(
            all(
                d["evidence"] and any(d["evidence"] in a for a in answers)
                for d in result["difficulties"]
            ),
            "困难说明必须引用学生实际回答。",
        )
    if stage == "feedback":
        require(result.get("feedback") and result.get("next_steps"), "模型未返回练习反馈和下一步。")
    if activity["kind"] == "lesson_plan":
        require(result.get("markdown", "").strip(), "模型未返回教案正文。")
    return result


def validate_citations(citations, sources):
    lookup = {
        (s.get("material_id"), s.get("document_id"), p["segment_id"]): p["text"]
        for s in sources["items"]
        for p in s["segments"]
    }
    for cite in citations:
        text = lookup.get((cite.get("material_id"), cite.get("document_id"), cite["segment_id"]))
        require(
            text is not None and cite["quote"].strip() and cite["quote"] in text,
            "模型引用未能与实际原文核对，请重试。",
        )
