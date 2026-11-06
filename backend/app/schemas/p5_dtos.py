"""External DTOs for P5 publication, learning reports, and teacher reporting."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, StrictBool, model_validator

from app.schemas.common import APIModel
from app.schemas.contracts import ReportContent, ReportMetrics, ReportScope


class PublishRequest(APIModel):
    confirmation_id: str


class PublishResult(APIModel):
    task_id: str
    version_id: str
    version_no: int
    status: Literal["published"]
    published_at: str
    task_revision: int


class ArchiveRequest(APIModel):
    confirmation_id: str
    expected_task_revision: int = Field(gt=0)


class RestoreRequest(APIModel):
    expected_task_revision: int = Field(gt=0)


class TaskStatusResult(APIModel):
    task_id: str
    status: Literal["active", "archived"]
    task_revision: int


class EndSessionResult(APIModel):
    session_id: str
    status: Literal["ended"]
    report_id: str | None = None
    report_status: Literal["queued", "generating", "ready", "failed", "superseded"] | None = None


class NoteCreateRequest(APIModel):
    message_id: str
    block_index: int = Field(ge=0)
    judgment: str = Field(default="", max_length=2000)
    credibility: Literal["unassessed", "high", "medium", "low"] = "unassessed"
    limitations: str = Field(default="", max_length=2000)


class NotePatchRequest(APIModel):
    judgment: str | None = Field(default=None, max_length=2000)
    credibility: Literal["unassessed", "high", "medium", "low"] | None = None
    limitations: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("at least one note field is required")
        return self


class NoteView(APIModel):
    id: str
    session_id: str
    message_id: str
    block_index: int
    original_view: str
    type: Literal["fact", "opinion", "inference", "unknown"]
    evidence_ids: list[str]
    judgment: str
    credibility: Literal["unassessed", "high", "medium", "low"]
    limitations: str
    row_version: int
    created_at: str
    updated_at: str


class NotePage(APIModel):
    items: list[NoteView]
    next_cursor: str | None = None


class DeletedResult(APIModel):
    deleted: StrictBool


class LegacySubmissionView(APIModel):
    id: str
    session_id: str
    status: Literal["draft", "submitted"]
    content: dict[str, object]
    row_version: int
    submitted_at: str | None = None
    created_at: str
    updated_at: str


class LearningEventRequest(APIModel):
    type: Literal["source_open", "stance"]
    source_id: str | None = None
    message_id: str | None = None
    value: Literal["need_more_evidence", "agree_for_now", "alternative_explanation"] | None = None
    expected_row_version: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_shape(self):
        if self.type == "source_open":
            if not self.source_id or self.message_id is not None or self.value is not None:
                raise ValueError("source_open requires only sourceId")
        elif (
            not self.message_id
            or self.value is None
            or self.source_id is not None
            or self.expected_row_version is None
        ):
            raise ValueError("stance requires messageId, value and expectedRowVersion")
        return self


class LearningEventView(APIModel):
    id: str
    session_id: str
    type: Literal["source_open", "stance"]
    source_id: str | None = None
    message_id: str | None = None
    value: str | None = None
    row_version: int
    created_at: str
    updated_at: str


class LearningReportView(APIModel):
    id: str
    session_id: str
    report_no: int
    kind: Literal["live", "final"]
    status: Literal["queued", "generating", "ready", "failed", "superseded"]
    input_revision: int
    generated_at: str | None = None
    content: ReportContent | None = None
    metrics: ReportMetrics
    source_tracking: Literal["complete", "partial", "unavailable"]


class ReportCorrectionRequest(APIModel):
    report_id: str
    text: str = Field(min_length=1, max_length=2000)


class ReportCorrectionView(APIModel):
    id: str
    session_id: str
    report_id: str
    author_id: str
    text: str
    created_at: str


class CorrectionPage(APIModel):
    items: list[ReportCorrectionView]
    next_cursor: str | None = None


class ReportEnvelope(APIModel):
    session_id: str
    session_status: Literal["active", "ended"]
    current_learning_revision: int
    current_report: LearningReportView | None = None
    latest_ready_report: LearningReportView | None = None
    freshness: Literal["empty", "updating", "current", "failed"]
    corrections: list[ReportCorrectionView]
    next_correction_cursor: str | None = None
    legacy_submission: LegacySubmissionView | None = None


class ReportQueueResult(APIModel):
    report_id: str | None = None
    status: Literal["empty", "queued", "generating", "ready", "failed", "superseded"]


class CoverageView(APIModel):
    total_sessions: int
    ready_report_sessions: int
    current_report_sessions: int
    source_tracked_sessions: int
    partial_source_sessions: int
    unavailable_source_sessions: int


class KPIView(APIModel):
    participant_count: int
    session_count: int
    completed_turns: int
    completed_report_count: int


class ProgressView(APIModel):
    active_sessions: int
    ended_sessions: int


class VersionLabel(APIModel):
    id: str
    version_no: int


class StudentReportRow(APIModel):
    user_id: str
    display_name: str
    session_id: str
    version_id: str
    version_no: int
    status: Literal["active", "ended"]
    metrics: ReportMetrics
    report_id: str | None = None
    report_status: str | None = None
    report_freshness: Literal["empty", "updating", "current", "failed"]
    source_tracking: Literal["complete", "partial", "unavailable"]
    correction_count: int


class ClassroomSummary(APIModel):
    text: str
    session_ids: list[str]


class TeachingSuggestion(APIModel):
    text: str
    session_ids: list[str]
    message_ids: list[str]


class TeacherReport(APIModel):
    task_id: str
    scope: Literal["latest", "all", "version"]
    version_id: str | None = None
    versions: list[VersionLabel]
    as_of: str
    aggregate_token: str
    kpis: KPIView
    progress: ProgressView
    metrics: ReportMetrics
    coverage: CoverageView
    classroom_summary: ClassroomSummary
    suggestions: list[TeachingSuggestion]
    students: list[StudentReportRow]
    next_cursor: str | None = None


class ReportDetailItem(APIModel):
    session_id: str
    student_name: str
    report_id: str | None = None
    message_id: str | None = None
    quote: str | None = None
    source_id: str | None = None
    source_name: str | None = None
    stance_value: str | None = None


class ReportDetails(APIModel):
    items: list[ReportDetailItem]
    next_cursor: str | None = None
    aggregate_token: str


class EvaluationResults(APIModel):
    role_consistency: Literal["pass", "fail", "not_applicable"] | None = None
    source_accuracy: Literal["pass", "fail", "not_applicable"] | None = None
    knowledge_boundary: Literal["pass", "fail", "not_applicable"] | None = None
    inquiry_depth: Literal["pass", "fail", "not_applicable"] | None = None


class EvaluationRequest(APIModel):
    message_ids: list[str] = Field(default_factory=list)
    results: EvaluationResults = Field(default_factory=EvaluationResults)
    note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def require_observation(self):
        if not self.note.strip() and not self.results.model_dump(exclude_none=True):
            raise ValueError("an evaluation result or note is required")
        return self


class ReviewCreated(APIModel):
    review_id: str


class TeachingReviewView(APIModel):
    id: str
    category: str
    summary: str
    message_id: str | None = None
    block_index: int | None = None
    citations: list[dict[str, object]] = Field(default_factory=list)


class TeachingReviewPage(APIModel):
    items: list[TeachingReviewView]
    next_cursor: str | None = None


class ExportRequest(APIModel):
    scope: Literal["latest", "all", "version"] = "latest"
    version_id: str | None = None
    aggregate_token: str

    @model_validator(mode="after")
    def validate_scope(self):
        ReportScope(scope=self.scope, version_id=self.version_id)
        return self
