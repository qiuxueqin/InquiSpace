"""External DTOs for P4 role sessions, messages, and dialogue actions."""

from typing import Literal

from pydantic import Field

from app.schemas.common import APIModel
from app.schemas.contracts import AnswerBlock


class EmptyRequest(APIModel):
    pass


class PublicRole(APIModel):
    role_id: str
    name: str
    role_type: Literal["real_historical", "fictional_composite"]
    identity_description: str
    time_anchor: dict[str, object] | None = None
    opening_message: str
    recommended_questions: list[str]


class RoleSessionView(APIModel):
    id: str
    task_id: str
    version_id: str
    version_revision: int
    owner_id: str
    mode: Literal["preview", "student"]
    status: Literal["active", "ended"]
    completed_turns: int
    learning_revision: int
    source_tracking: Literal["complete", "partial", "unavailable"]
    public_role: PublicRole
    summary: dict[str, object]
    created_at: str
    ended_at: str | None = None


class CitationView(APIModel):
    id: str
    message_id: str
    block_index: int
    evidence_id: str
    source_id: str
    file_name: str
    page_no: int | None = None
    start_line: int | None = None
    end_line: int | None = None
    paragraph_no: int
    quote: str


class MessageMeta(APIModel):
    role_id: str | None = None
    role_type: str | None = None
    time_anchor: dict[str, object] | None = None
    follow_up_questions: list[str] = Field(default_factory=list)
    phase: str | None = None
    memory_summary: str | None = None


class MessageView(APIModel):
    id: str
    session_id: str
    seq: int
    speaker: Literal["user", "assistant"]
    status: Literal["pending", "partial", "complete", "discarded"]
    text: str
    blocks: list[AnswerBlock]
    citations: list[CitationView]
    run_id: str | None = None
    supersedes_message_id: str | None = None
    meta: MessageMeta
    created_at: str


class MessagePage(APIModel):
    items: list[MessageView]
    next_after_seq: int
    has_more: bool


class SendMessageRequest(APIModel):
    content: str = Field(min_length=1, max_length=4000)


class StartedMessageRun(APIModel):
    user_message_id: str
    assistant_message_id: str
    run_id: str


class SummaryResult(APIModel):
    summary: str
    unresolved_questions: list[str]


class SessionListItem(APIModel):
    id: str
    version_id: str
    version_no: int
    status: Literal["active", "ended"]
    completed_turns: int
    created_at: str


class SessionPage(APIModel):
    items: list[SessionListItem]
    next_cursor: str | None = None


class CancelRunRequest(APIModel):
    reason: str | None = Field(default=None, max_length=500)


class CancelRunResult(APIModel):
    run_id: str
    cancel_requested: bool
    status: str
