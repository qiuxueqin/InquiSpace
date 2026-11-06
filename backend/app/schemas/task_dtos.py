"""HTTP DTOs for task and draft/version endpoints.

These models intentionally remain separate from SQLModel rows.  DraftTaskBrief is
partial by design: a draft may be incomplete, while the publication workflow will
later enforce the complete TaskBrief contract.
"""

from typing import Any

from pydantic import Field

from app.schemas.common import APIModel
from app.schemas.contracts import DraftTaskBrief, QuestionPlanItem


class CreateTaskRequest(APIModel):
    brief: DraftTaskBrief | None = None
    teaching_intent: str | None = None


class PatchVersionRequest(APIModel):
    teaching_intent: str | None = None
    brief: DraftTaskBrief | None = None
    question_plan: list[QuestionPlanItem] | None = None


class CopyVersionRequest(APIModel):
    from_version_id: str


class TaskListItem(APIModel):
    task_id: str
    topic_name: str
    status: str
    current_published_version_id: str | None = None


class TaskListPage(APIModel):
    items: list[TaskListItem]
    next_cursor: str | None = None


class VersionSummary(APIModel):
    id: str
    task_id: str
    version_no: int
    revision: int
    status: str
    teaching_intent: str
    created_at: str
    updated_at: str
    published_at: str | None = None
    from_version_id: str | None = None


class VersionListPage(APIModel):
    items: list[VersionSummary]
    next_cursor: str | None = None


class VersionView(APIModel):
    id: str
    task_id: str
    version_no: int
    revision: int
    status: str
    from_version_id: str | None = None
    teaching_intent: str
    brief: dict[str, Any]
    question_plan: list[dict[str, Any]]
    role_card: dict[str, Any] | None = None
    source_ids: list[str] = Field(default_factory=list)
    manual_fields: list[str] = Field(default_factory=list)
    generation_meta: dict[str, Any] = Field(default_factory=dict)
    validation_status: str
    validated_revision: int | None = None
    preview_revision: int | None = None
    created_at: str
    updated_at: str
    published_at: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)


class TaskDetail(APIModel):
    id: str
    status: str
    task_revision: int
    current_published_version_id: str | None = None
    draft_version_id: str | None = None
    public_brief: dict[str, Any] | None = None
    public_role: dict[str, Any] | None = None


class IdempotencyData(APIModel):
    """Marker used by route annotations for JSON data returned by writes."""

    data: dict[str, Any]
