"""P0 public DTOs, not persistence models or proof of authorization/readiness.

Validators cover local structure only. Services must still check object ownership,
source readiness, evidence support, verbatim student quotes, semantic constraints,
and publication checks. In particular a valid UUID is not an authorized reference.

Register PUBLIC_SCHEMAS with pydantic.json_schema.models_json_schema using
ref_template='#/components/schemas/{model}', then merge its $defs into OpenAPI
components.schemas. No placeholder business routes are needed. RunView is generic:
future endpoints must bind it to an explicitly allowlisted public result DTO,
never dict/Any or an internal Run model. The unbound base permits only an empty
APIModel result; the registered specializations describe the two P0 result types.
"""

import re
from datetime import UTC, date
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    Field,
    StrictBool,
    StringConstraints,
    model_validator,
)

from app.schemas.common import APIModel

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
UTCDatetime = Annotated[AwareDatetime, AfterValidator(lambda value: value.astimezone(UTC))]
RoleType = Literal["real_historical", "fictional_composite"]


class TimeAnchor(APIModel):
    value: str
    precision: Literal["year", "month", "day"]

    @model_validator(mode="after")
    def validate_calendar_value(self) -> Self:
        patterns = {
            "year": r"[0-9]{4}",
            "month": r"[0-9]{4}-[0-9]{2}",
            "day": r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
        }
        if not re.fullmatch(patterns[self.precision], self.value):
            raise ValueError("timeAnchor value must match its precision")
        # Validate without inventing a month/day in the stored anchor.
        parts = [int(part) for part in self.value.split("-")]
        date(*parts, *([1] * (3 - len(parts))))
        return self


class MaterialPolicy(APIModel):
    external_knowledge_allowed: StrictBool = False
    external_knowledge_scope: str = ""

    @model_validator(mode="after")
    def require_external_scope(self) -> Self:
        if self.external_knowledge_allowed and not self.external_knowledge_scope.strip():
            raise ValueError("external knowledge requires an explicit scope")
        return self


class Restrictions(APIModel):
    max_turns: PositiveInt
    suggested_minutes: PositiveInt
    deadline_at: UTCDatetime | None
    difficulty: NonEmptyText
    forbidden_content: list[NonEmptyText]


# Explicit wire-path allowlist; never accept arbitrary object/array traversal.
ConfirmedField = Literal[
    "topicName",
    "background",
    "subject",
    "grade",
    "learningGoals",
    "coreQuestion",
    "isHistoricalTopic",
    "timeAnchor",
    "region",
    "roleType",
    "roleName",
    "materialPolicy",
    "materialPolicy.externalKnowledgeAllowed",
    "materialPolicy.externalKnowledgeScope",
    "restrictions",
    "restrictions.maxTurns",
    "restrictions.suggestedMinutes",
    "restrictions.deadlineAt",
    "restrictions.difficulty",
    "restrictions.forbiddenContent",
    "expectedOutcome",
]


class DraftTaskBrief(APIModel):
    """Incomplete draft; explicit nested objects replace whole nested values.

    Unset fields remain distinguishable from null via model_fields_set and
    model_dump(exclude_unset=True). This is not a publication-ready brief.
    """

    topic_name: str | None = None
    background: str | None = None
    subject: str | None = None
    grade: str | None = None
    learning_goals: list[NonEmptyText] | None = None
    core_question: str | None = None
    is_historical_topic: StrictBool | None = None
    time_anchor: TimeAnchor | None = None
    region: str | None = None
    role_type: RoleType | None = None
    role_name: str | None = None
    material_policy: MaterialPolicy | None = None
    restrictions: Restrictions | None = None
    expected_outcome: str | None = None
    confirmed_fields: list[ConfirmedField] = Field(default_factory=list)


class TaskBrief(APIModel):
    """Complete publication shape, not a claim that publication checks passed."""

    topic_name: NonEmptyText
    background: NonEmptyText
    subject: NonEmptyText
    grade: NonEmptyText
    learning_goals: Annotated[list[NonEmptyText], Field(min_length=1)]
    core_question: NonEmptyText
    is_historical_topic: StrictBool
    time_anchor: TimeAnchor | None
    region: NonEmptyText | None
    role_type: RoleType
    role_name: NonEmptyText
    material_policy: MaterialPolicy = Field(default_factory=MaterialPolicy)
    restrictions: Restrictions
    expected_outcome: NonEmptyText
    confirmed_fields: list[ConfirmedField] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_historical_anchor(self) -> Self:
        if self.role_type == "real_historical" and not self.is_historical_topic:
            raise ValueError("real historical roles require a historical topic")
        if self.is_historical_topic and self.time_anchor is None:
            raise ValueError("historical topics require a timeAnchor")
        return self


class Relationship(APIModel):
    target: NonEmptyText
    description: NonEmptyText


class KnownFact(APIModel):
    text: NonEmptyText
    evidence_ids: list[UUID]
    origin: Literal["material", "teacher"]

    @model_validator(mode="after")
    def require_material_reference(self) -> Self:
        if self.origin == "material" and not self.evidence_ids:
            raise ValueError("material facts require evidenceIds")
        return self


class DisputedClaim(APIModel):
    text: NonEmptyText
    evidence_ids: list[UUID]
    limitation: NonEmptyText


class RoleCardInput(APIModel):
    """Candidate shape: roleId is forbidden, not silently discarded.

    Mandatory behavioral meanings (no fabrication, overreach, or ghostwriting)
    and consistency with the brief require service-level checks, not substring
    matching against a list of Chinese phrases.
    """

    name: NonEmptyText
    role_type: RoleType
    identity_description: NonEmptyText
    historical_period: NonEmptyText
    time_anchor: TimeAnchor | None
    region: NonEmptyText
    social_group: NonEmptyText
    position: NonEmptyText
    goals: list[NonEmptyText]
    concerns: list[NonEmptyText]
    relationships: list[Relationship]
    known_facts: list[KnownFact]
    unknown_facts: list[NonEmptyText]
    source_ids: list[UUID]
    disputed_claims: list[DisputedClaim]
    speech_style: NonEmptyText
    opening_message: NonEmptyText
    recommended_questions: Annotated[list[NonEmptyText], Field(min_length=1, max_length=3)]
    learning_dimension: NonEmptyText
    forbidden_behaviors: Annotated[list[NonEmptyText], Field(min_length=1)]

    @model_validator(mode="after")
    def require_real_historical_anchor(self) -> Self:
        if self.role_type == "real_historical" and self.time_anchor is None:
            raise ValueError("real historical roles require a timeAnchor")
        return self


class RoleCard(RoleCardInput):
    role_id: UUID


class QuestionPlanItem(APIModel):
    question: NonEmptyText
    dimension: NonEmptyText
    purpose: NonEmptyText


# Wire format is an array, not {items: [...]}. Drafts may use list[QuestionPlanItem].
QuestionPlan = Annotated[list[QuestionPlanItem], Field(min_length=1)]


class AnswerBlock(APIModel):
    block_index: NonNegativeInt
    type: Literal["fact", "opinion", "inference", "unknown"]
    text: NonEmptyText
    evidence_ids: list[UUID]

    @model_validator(mode="after")
    def require_fact_references(self) -> Self:
        if self.type == "fact" and not self.evidence_ids:
            raise ValueError("fact blocks require evidenceIds; support is checked by services")
        return self


def _continuous_blocks(blocks: list[AnswerBlock]) -> list[AnswerBlock]:
    if [block.block_index for block in blocks] != list(range(len(blocks))):
        raise ValueError("blockIndex must be consecutive starting at zero")
    return blocks


AnswerBlocks = Annotated[list[AnswerBlock], AfterValidator(_continuous_blocks)]


class RunError(APIModel):
    code: NonEmptyText
    message: NonEmptyText
    retryable: StrictBool


class BlockingIssue(APIModel):
    field: NonEmptyText | None = None
    message: NonEmptyText


class PublishReadiness(APIModel):
    ready: StrictBool
    state: Literal["preparing", "needs_input", "ready", "unavailable"]
    revision: PositiveInt
    task_revision: PositiveInt
    content_hash: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    blocking_issues: list[BlockingIssue]
    next_questions: Annotated[list[NonEmptyText], Field(max_length=3)]

    @model_validator(mode="after")
    def consistent_ready_state(self) -> Self:
        if self.ready != (self.state == "ready"):
            raise ValueError("ready must agree with state")
        if self.ready and (self.blocking_issues or self.next_questions):
            raise ValueError("ready cannot have blockers or required questions")
        return self


class ReportRunResult(APIModel):
    report_id: UUID


class RunView[ResultT: APIModel](APIModel):
    """Public projection only; caller must select results appropriate to the viewer."""

    id: UUID
    kind: Literal[
        "parse_material",
        "role_generate",
        "role_validate",
        "plan_generate",
        "publish_preflight",
        "chat",
        "summary",
        "learning_report",
    ]
    status: Literal["running", "waiting_confirmation", "completed", "failed", "cancelled"]
    display_message: NonEmptyText
    session_id: UUID | None
    version_id: UUID | None
    result: ResultT | None
    error: RunError | None
    created_at: UTCDatetime
    finished_at: UTCDatetime | None

    @model_validator(mode="after")
    def chronological_times(self) -> Self:
        if self.finished_at is not None and self.finished_at < self.created_at:
            raise ValueError("finishedAt cannot precede createdAt")
        return self


class ReportSummary(APIModel):
    text: NonEmptyText
    message_ids: list[UUID]


class ReportFinding(APIModel):
    kind: Literal[
        "student_judgment",
        "evidence_seeking",
        "counterargument",
        "view_change",
        "reflection",
        "unresolved",
        "role_view",
    ]
    text: NonEmptyText
    message_ids: Annotated[list[UUID], Field(min_length=1)]
    evidence_ids: list[UUID]

    @model_validator(mode="after")
    def require_change_references(self) -> Self:
        if self.kind == "view_change" and len(set(self.message_ids)) < 2:
            raise ValueError("view_change requires distinct before and after messages")
        return self


class ReportSignal(APIModel):
    message_id: UUID
    # Preserve whitespace: services must check a verbatim substring, not trimmed text.
    quote: Annotated[str, StringConstraints(min_length=1)]
    tags: Annotated[
        list[Literal["evidence_seeking", "judgment", "reflection"]],
        Field(min_length=1, max_length=3),
    ]

    @model_validator(mode="after")
    def unique_tags(self) -> Self:
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("signal tags must be unique")
        if not self.quote.strip():
            raise ValueError("quote must contain non-whitespace text")
        return self


class ReportContent(APIModel):
    """Shape only; does not certify student attribution, quotes, or semantic truth."""

    summary: ReportSummary
    findings: list[ReportFinding]
    signals: list[ReportSignal]
    missing_aspects: list[NonEmptyText]
    next_steps: list[NonEmptyText]

    @model_validator(mode="after")
    def unique_signal_messages(self) -> Self:
        ids = [signal.message_id for signal in self.signals]
        if len(ids) != len(set(ids)):
            raise ValueError("at most one signal per student message")
        return self


class ReportMetrics(APIModel):
    """Program-computed counts. Explicit null means unknown, never default to zero.

    All fields allow null because teacher aggregates can have no usable basis.
    Session-level services must supply the actual expression count when known.
    """

    expression_count: NonNegativeInt | None
    evidence_seeking_count: NonNegativeInt | None
    source_view_count: NonNegativeInt | None
    judgment_count: NonNegativeInt | None
    reflection_count: NonNegativeInt | None


class ReportScope(APIModel):
    scope: Literal["latest", "all", "version"] = "latest"
    version_id: UUID | None = None
    state: Literal["all", "active", "ended"] = "all"

    @model_validator(mode="after")
    def require_version_scope(self) -> Self:
        if (self.scope == "version") != (self.version_id is not None):
            raise ValueError("versionId is required and only allowed for version scope")
        return self


class PaginationParams(APIModel):
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 20
    cursor: NonEmptyText | None = None


class Page[ItemT](APIModel):
    items: list[ItemT]
    next_cursor: NonEmptyText | None


PUBLIC_SCHEMAS = (
    TimeAnchor,
    MaterialPolicy,
    Restrictions,
    DraftTaskBrief,
    TaskBrief,
    RoleCardInput,
    RoleCard,
    QuestionPlanItem,
    AnswerBlock,
    RunError,
    PublishReadiness,
    ReportRunResult,
    RunView,
    RunView[ReportRunResult],
    RunView[PublishReadiness],
    ReportContent,
    ReportMetrics,
    ReportScope,
    PaginationParams,
    Page[RoleCard],
)
