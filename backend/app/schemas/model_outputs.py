"""P3 model-facing schemas; role IDs and workflow authority stay server-side."""

from typing import Literal

from pydantic import ConfigDict, Field, StrictBool, model_validator

from app.schemas.common import APIModel
from app.schemas.contracts import AnswerBlock, DraftTaskBrief, QuestionPlanItem, RoleCardInput
from app.schemas.p3_dtos import PreflightCheckView, ValidationIssueView


class Coverage(APIModel):
    covered_goals: list[str]
    gaps: list[str]
    disputes: list[str]
    risks: list[str]


class RoleCandidate(APIModel):
    role_card: RoleCardInput
    recommendation_reason: str = Field(min_length=1)
    question_plan: list[QuestionPlanItem] = Field(min_length=1)
    coverage: Coverage


PlanMissingField = Literal[
    "topicName",
    "background",
    "learningGoals",
    "coreQuestion",
    "timeAnchor",
    "region",
    "roleName",
]


class GeneratedPlan(APIModel):
    model_config = ConfigDict(
        alias_generator=APIModel.model_config["alias_generator"],
        populate_by_name=True,
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "brief": {
                        "topicName": "达尔文研究进化论的过程",
                        "background": "探究科学解释如何在观察与证据中形成。",
                        "subject": "生物",
                        "grade": "九年级",
                        "learningGoals": ["理解观察、证据与科学解释的关系"],
                        "coreQuestion": "达尔文如何通过观察和证据形成进化论解释？",
                        "isHistoricalTopic": True,
                        "timeAnchor": None,
                        "region": None,
                        "roleType": "real_historical",
                        "roleName": "查尔斯·达尔文",
                        "materialPolicy": {
                            "externalKnowledgeAllowed": False,
                            "externalKnowledgeScope": "",
                        },
                        "restrictions": {
                            "maxTurns": 20,
                            "suggestedMinutes": 45,
                            "deadlineAt": None,
                            "difficulty": "九年级",
                            "forbiddenContent": [],
                        },
                        "expectedOutcome": "依据材料解释科学认识的形成过程",
                        "confirmedFields": [],
                    },
                    "roleCard": None,
                    "questionPlan": [],
                    "assumptions": ["采用默认课时"],
                    "missingFields": ["timeAnchor"],
                    "nextQuestions": ["希望角色处于达尔文研究过程中的哪个年份？"],
                }
            ]
        },
    )

    brief: DraftTaskBrief
    role_card: RoleCardInput | None = None
    question_plan: list[QuestionPlanItem] = Field(default_factory=list)
    assumptions: list[str]
    missing_fields: list[PlanMissingField] = Field(default_factory=list, max_length=3)
    next_questions: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def coherent_draft_or_complete_plan(self):
        has_missing = bool(self.missing_fields)
        if has_missing != bool(self.next_questions):
            raise ValueError("missing fields and questions must be supplied together")
        if not has_missing and (self.role_card is None or not self.question_plan):
            raise ValueError("complete plans require a role card and question plan")
        if self.role_card is not None:
            if self.brief.role_name is not None and self.brief.role_name != self.role_card.name:
                raise ValueError("brief and role card names must match")
            if (
                self.brief.role_type is not None
                and self.brief.role_type != self.role_card.role_type
            ):
                raise ValueError("brief and role card types must match")
            if (
                self.brief.time_anchor is not None
                and self.role_card.time_anchor != self.brief.time_anchor
            ):
                raise ValueError("brief and role card time anchors must match")
        return self


class RoleValidationOutput(APIModel):
    passed: StrictBool
    issues: list[ValidationIssueView]

    @model_validator(mode="after")
    def result_matches_issues(self):
        blocking = any(issue.severity == "error" for issue in self.issues)
        if self.passed == blocking:
            raise ValueError("passed must agree with blocking issues")
        return self


class PreflightOutput(APIModel):
    checks: list[PreflightCheckView]

    @model_validator(mode="after")
    def categories_are_complete(self):
        expected = {
            "identity",
            "future_information",
            "private_motives",
            "viewpoint_conflict",
            "prompt_injection",
        }
        actual = [item.category for item in self.checks]
        if set(actual) != expected or len(actual) != len(expected):
            raise ValueError("all five unique preflight categories are required")
        return self


class InternalIssue(APIModel):
    code: str
    severity: Literal["warning", "error"]
    message: str
    field: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class DialogueLine(APIModel):
    type: Literal["fact", "opinion", "inference", "unknown"]
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class AnswerCheckOutput(APIModel):
    passed: StrictBool
    issues: list[InternalIssue] = Field(default_factory=list)
    repaired_block: AnswerBlock | None = None

    @model_validator(mode="after")
    def result_is_consistent(self):
        if self.passed and any(issue.severity == "error" for issue in self.issues):
            raise ValueError("passed answer checks cannot contain blocking issues")
        return self


class ConversationSummaryOutput(APIModel):
    student_views: list[str] = Field(default_factory=list)
    verified_facts: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    prior_follow_ups: list[str] = Field(default_factory=list)


class FollowUpOutput(APIModel):
    follow_up_questions: list[str] = Field(default_factory=list, max_length=3)
