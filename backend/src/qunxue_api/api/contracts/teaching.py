from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class RubricDimension(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    max_score: float = Field(gt=0, le=1000)


class TeachingAnswer(StrictModel):
    question_id: str
    answer: str = Field(max_length=20000)


class TeachingInput(StrictModel):
    title: str = Field(default="", max_length=200)
    objectives: str = Field(default="", max_length=10000)
    duration_minutes: int = Field(default=45, ge=1, le=600)
    student_background: str = Field(default="", max_length=10000)
    requirements: str = Field(default="", max_length=20000)
    difficulties: str = Field(default="", max_length=10000)
    submission_text: str = Field(default="", max_length=50000)
    material_ids: list[UUID] = Field(default_factory=list, max_length=20)
    course_document_ids: list[UUID] = Field(default_factory=list, max_length=20)
    rubric: list[RubricDimension] = Field(default_factory=list, max_length=5)
    diagnostic_answers: list[TeachingAnswer] = Field(default_factory=list, max_length=3)
    practice_answer: str = Field(default="", max_length=20000)
    settings_version: int = 0
    improvement_context: str = Field(default="", max_length=20000)
    source_activity_ids: list[UUID] = Field(default_factory=list, max_length=20)


class TeachingCitation(StrictModel):
    material_id: str | None = None
    document_id: str | None = None
    segment_id: str
    title: str
    quote: str


class TeachingScore(StrictModel):
    dimension_id: str
    score: float | None = Field(default=None, ge=0)
    rationale: str
    citations: list[TeachingCitation] = Field(default_factory=list)


class TeachingQuestion(StrictModel):
    id: str
    prompt: str


class TeachingDifficulty(StrictModel):
    description: str
    evidence: str


class TeachingRecommendation(StrictModel):
    title: str
    reason: str
    source: TeachingCitation


class TeachingPractice(StrictModel):
    prompt: str


class TeachingResult(StrictModel):
    stage: Literal["diagnostic", "practice", "feedback", "complete"] = "complete"
    markdown: str = ""
    diagnostic_questions: list[TeachingQuestion] = Field(default_factory=list)
    difficulties: list[TeachingDifficulty] = Field(default_factory=list)
    recommendations: list[TeachingRecommendation] = Field(default_factory=list)
    practice: TeachingPractice | None = None
    feedback: str = ""
    next_steps: list[str] = Field(default_factory=list)
    suggested_scores: list[TeachingScore] = Field(default_factory=list)
    teacher_scores: list[TeachingScore] = Field(default_factory=list)
    teacher_feedback: str = ""
    citations: list[TeachingCitation] = Field(default_factory=list)


class TeachingActivity(StrictModel):
    id: str
    course_id: str
    owner_user_id: str
    kind: Literal["lesson_plan", "assignment_review", "learning_check"]
    state: Literal["draft", "running", "ready", "reviewed", "published", "failed"]
    version: int
    input: TeachingInput
    result: TeachingResult | None = None
    shared_with_teacher: bool
    source_activity_id: str | None = None
    agent_run_id: str | None = None
    conversation_id: str | None = None
    task_id: str | None = None
    document_id: str | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str


class CreateTeachingActivity(StrictModel):
    kind: Literal["lesson_plan", "assignment_review", "learning_check"]
    input: TeachingInput
    shared_with_teacher: bool = False
    source_activity_id: UUID | None = None


class TeachingVersion(StrictModel):
    version: int = Field(ge=1)


class UpdateTeachingActivity(TeachingVersion):
    input: TeachingInput | None = None
    shared_with_teacher: bool | None = None
    teacher_scores: list[TeachingScore] | None = None
    teacher_feedback: str | None = Field(default=None, max_length=50000)
    reviewed: bool | None = None
    document_markdown: str | None = Field(default=None, max_length=200000)
    revision_instruction: str | None = Field(default=None, max_length=10000)
    selected_text: str | None = Field(default=None, max_length=20000)

    @model_validator(mode="after")
    def reject_explicit_null(self):
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("修改字段不能为null；未修改字段请省略。")
        return self


class TeachingSettings(StrictModel):
    course_id: str
    objectives: str
    rubric: list[RubricDimension]
    version: int


class UpdateTeachingSettings(StrictModel):
    version: int = Field(ge=0)
    objectives: str = Field(max_length=10000)
    rubric: list[RubricDimension] = Field(max_length=5)


class TeachingSegment(StrictModel):
    segment_id: str
    text: str


class TeachingSourceItem(StrictModel):
    material_id: str | None = None
    document_id: str | None = None
    title: str
    segments: list[TeachingSegment]


class TeachingSource(StrictModel):
    items: list[TeachingSourceItem]


class TeachingActivityList(StrictModel):
    items: list[TeachingActivity]


class LearningIssue(StrictModel):
    description: str
    activity_ids: list[str]
    evidence: list[str]


class LearningSummary(StrictModel):
    sample_count: int
    issues: list[LearningIssue]
    updated_at: str | None = None
