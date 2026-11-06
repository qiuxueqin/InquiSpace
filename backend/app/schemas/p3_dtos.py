"""External DTOs for P3 plan, role, validation, preflight, and confirmation APIs."""

from typing import Literal

from pydantic import Field, StrictBool, model_validator

from app.schemas.common import APIModel
from app.schemas.contracts import RoleCardInput
from app.schemas.material_dtos import RunView
from app.schemas.task_dtos import VersionView


class RoleGenerationRequest(APIModel):
    instruction: str | None = Field(default=None, max_length=2000)


class SaveRoleCardRequest(APIModel):
    role_card: RoleCardInput


class ApplyRoleCandidateRequest(APIModel):
    confirmation_id: str


class AppliedRoleCandidate(APIModel):
    role_card: dict[str, object]
    question_plan: list[dict[str, object]]
    revision: int


class PlanGenerationRequest(APIModel):
    confirmation_id: str | None = None


class PlanGenerationResult(APIModel):
    version: VersionView
    undo_available: StrictBool


class ValidationIssueView(APIModel):
    code: str
    severity: Literal["warning", "error"]
    message: str
    field: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class ValidationResultView(APIModel):
    valid: StrictBool
    issues: list[ValidationIssueView]
    review_id: str
    validated_revision: int | None = None


class PreflightCheckView(APIModel):
    category: Literal[
        "identity",
        "future_information",
        "private_motives",
        "viewpoint_conflict",
        "prompt_injection",
    ]
    result: Literal["pass", "fail", "not_applicable"]
    reason: str
    message: str | None = None


class ConfirmationPayload(APIModel):
    run_id: str | None = None
    candidate_hash: str | None = None
    intent_hash: str | None = None
    overwritten_fields: list[str] | None = None
    student_ids: list[str] | None = None


class CreateConfirmationRequest(APIModel):
    action: Literal["publish_version", "apply_role_candidate", "archive_task", "replace_plan"]
    confirmed: StrictBool
    task_revision: int = Field(gt=0)
    payload: ConfirmationPayload

    @model_validator(mode="after")
    def validate_action_payload(self):
        if not self.confirmed:
            raise ValueError("confirmed must be true")
        supplied = self.payload.model_dump(exclude_none=True)
        if self.action == "apply_role_candidate":
            if not self.payload.run_id or not self.payload.candidate_hash:
                raise ValueError("candidate confirmation requires runId and candidateHash")
            if set(supplied) != {"run_id", "candidate_hash"}:
                raise ValueError("candidate confirmation contains unrelated fields")
        elif self.action == "replace_plan":
            if not self.payload.intent_hash or self.payload.overwritten_fields is None:
                raise ValueError("replace confirmation requires intentHash and overwrittenFields")
            if set(supplied) != {"intent_hash", "overwritten_fields"}:
                raise ValueError("replace confirmation contains unrelated fields")
        elif self.action == "publish_version":
            if self.payload.student_ids is None or set(supplied) != {"student_ids"}:
                raise ValueError("publish confirmation requires studentIds")
        elif supplied:
            raise ValueError("archive confirmation payload must be empty")
        return self


class ConfirmationView(APIModel):
    confirmation_id: str
    action: str
    version_revision: int
    expires_at: str


class CancelRunRequest(APIModel):
    reason: str | None = Field(default=None, max_length=500)


class CancelRunResult(APIModel):
    run_id: str
    cancel_requested: StrictBool
    run: RunView | None = None


class StartedRun(APIModel):
    run: RunView


class EmptyRequest(APIModel):
    pass
