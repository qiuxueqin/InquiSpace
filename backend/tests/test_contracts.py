"""Structural contract tests; no database, model calls or authorization claims."""

from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError
from pydantic.json_schema import models_json_schema

from app.schemas.contracts import (
    PUBLIC_SCHEMAS,
    AnswerBlock,
    AnswerBlocks,
    DraftTaskBrief,
    KnownFact,
    MaterialPolicy,
    Page,
    PaginationParams,
    PublishReadiness,
    QuestionPlan,
    ReportContent,
    ReportFinding,
    ReportMetrics,
    ReportRunResult,
    ReportScope,
    ReportSignal,
    Restrictions,
    RoleCard,
    RoleCardInput,
    RunView,
    TaskBrief,
    TimeAnchor,
)


def restrictions(**changes):
    return dict(
        maxTurns=10,
        suggestedMinutes=20,
        deadlineAt=None,
        difficulty="基础",
        forbiddenContent=[],
        **changes,
    )


def brief():
    return dict(
        topicName="水资源",
        background="校园用水",
        subject="科学",
        grade="七年级",
        learningGoals=["寻找依据"],
        coreQuestion="怎样节水？",
        isHistoricalTopic=False,
        timeAnchor=None,
        region=None,
        roleType="fictional_composite",
        roleName="观察员",
        restrictions=restrictions(),
        expectedOutcome="提出有依据的想法",
    )


def role():
    return dict(
        name="观察员",
        roleType="fictional_composite",
        identityDescription="社区观察员",
        historicalPeriod="非历史情境",
        timeAnchor=None,
        region="未限定",
        socialGroup="未限定",
        position="了解情况",
        goals=[],
        concerns=[],
        relationships=[],
        knownFacts=[],
        unknownFacts=[],
        sourceIds=[],
        disputedClaims=[],
        speechStyle="简洁",
        openingMessage="你想先了解什么？",
        recommendedQuestions=["有哪些依据？"],
        learningDimension="证据",
        forbiddenBehaviors=["不编造、不越界、不代写"],
    )


def run():
    return dict(
        id=str(uuid4()),
        kind="learning_report",
        status="running",
        displayMessage="整理中",
        sessionId=str(uuid4()),
        versionId=None,
        result=None,
        error=None,
        createdAt="2026-11-04T10:00:00+08:00",
        finishedAt=None,
    )


def report():
    return dict(
        summary={"text": "尚无表达", "messageIds": []},
        findings=[],
        signals=[],
        missingAspects=["尚未表达判断"],
        nextSteps=["可以先提出问题"],
    )


def test_draft_can_be_empty_or_incomplete_without_claiming_publishability():
    assert DraftTaskBrief().model_dump(exclude_unset=True) == {}
    draft = DraftTaskBrief.model_validate({"topicName": "", "isHistoricalTopic": True})
    assert draft.time_anchor is None
    assert draft.model_dump(by_alias=True, exclude_unset=True) == {
        "topicName": "",
        "isHistoricalTopic": True,
    }
    with pytest.raises(ValidationError):
        TaskBrief.model_validate(draft.model_dump(exclude_unset=True))


def test_complete_brief_round_trip_and_default_material_policy():
    value = TaskBrief.model_validate(brief())
    data = value.model_dump(mode="json", by_alias=True)
    assert data["materialPolicy"] == {
        "externalKnowledgeAllowed": False,
        "externalKnowledgeScope": "",
    }
    assert "topic_name" not in data
    assert TaskBrief.model_validate_json(value.model_dump_json(by_alias=True)) == value


@pytest.mark.parametrize(
    "patch",
    [
        {"topicName": "  "},
        {"learningGoals": []},
        {"roleType": "anything"},
        {"isHistoricalTopic": True},
        {"roleType": "real_historical"},
        {"confirmedFields": ["__class__"]},
        {"confirmedFields": ["restrictions.maxSteps"]},
        {"isHistoricalTopic": "false"},
    ],
)
def test_invalid_complete_brief(patch):
    with pytest.raises(ValidationError):
        TaskBrief.model_validate(brief() | patch)


@pytest.mark.parametrize(
    "value,precision",
    [
        ("0000", "year"),
        ("2026-13", "month"),
        ("2026-02-29", "day"),
        ("2024-04-31", "day"),
        ("2024-1", "month"),
        ("2024-01-01", "year"),
        ("2024", "century"),
    ],
)
def test_time_anchor_rejects_invalid_dates_and_precision(value, precision):
    with pytest.raises(ValidationError):
        TimeAnchor(value=value, precision=precision)


@pytest.mark.parametrize(
    "value,precision",
    [
        ("0001", "year"),
        ("2024-02", "month"),
        ("2024-02-29", "day"),
    ],
)
def test_time_anchor_preserves_precision(value, precision):
    assert TimeAnchor(value=value, precision=precision).value == value


@pytest.mark.parametrize(
    "patch",
    [
        {"maxTurns": 0},
        {"suggestedMinutes": -1},
        {"maxTurns": True},
        {"maxTurns": 1.2},
        {"deadlineAt": "2026-11-04T12:00:00"},
    ],
)
def test_restrictions_require_positive_integers_and_aware_timestamp(patch):
    with pytest.raises(ValidationError):
        Restrictions.model_validate(restrictions() | patch)


def test_material_policy_scope_is_required_only_when_enabled():
    MaterialPolicy()
    with pytest.raises(ValidationError):
        MaterialPolicy(external_knowledge_allowed=True, external_knowledge_scope=" ")
    assert MaterialPolicy(
        external_knowledge_allowed=True, external_knowledge_scope="背景"
    ).external_knowledge_allowed


def test_role_id_is_server_assigned_not_accepted_in_candidate():
    candidate = RoleCardInput.model_validate(role())
    for key in ("roleId", "role_id"):
        with pytest.raises(ValidationError):
            RoleCardInput.model_validate(role() | {key: str(uuid4())})
    stored = RoleCard.model_validate(role() | {"roleId": str(uuid4())})
    assert stored.name == candidate.name
    with pytest.raises(ValidationError):
        RoleCard.model_validate(role() | {"roleId": "not-a-uuid"})


@pytest.mark.parametrize(
    "patch",
    [
        {"recommendedQuestions": []},
        {"recommendedQuestions": ["a"] * 4},
        {"socialGroup": " "},
        {"forbiddenBehaviors": []},
        {"roleType": "real_historical"},
    ],
)
def test_role_card_necessary_structure(patch):
    with pytest.raises(ValidationError):
        RoleCardInput.model_validate(role() | patch)


def test_fact_references_and_continuous_block_indices():
    with pytest.raises(ValidationError):
        KnownFact(text="事实", origin="material", evidence_ids=[])
    KnownFact(text="教师输入", origin="teacher", evidence_ids=[])
    with pytest.raises(ValidationError):
        AnswerBlock(block_index=0, type="fact", text="事实", evidence_ids=[])
    fact = AnswerBlock(block_index=0, type="fact", text="事实", evidence_ids=[uuid4()])
    adapter = TypeAdapter(AnswerBlocks)
    assert adapter.validate_python([fact]) == [fact]
    with pytest.raises(ValidationError):
        adapter.validate_python([fact, fact])
    with pytest.raises(ValidationError):
        adapter.validate_python(
            [{"blockIndex": 1, "type": "unknown", "text": "未知", "evidenceIds": []}]
        )


def test_question_plan_is_nonempty_array():
    adapter = TypeAdapter(QuestionPlan)
    assert adapter.validate_python(
        [{"question": "为什么？", "dimension": "证据", "purpose": "追问"}]
    )
    with pytest.raises(ValidationError):
        adapter.validate_python([])


def test_run_normalizes_utc_and_uses_explicit_public_result():
    model = RunView[ReportRunResult].model_validate(run() | {"result": {"reportId": str(uuid4())}})
    data = model.model_dump(mode="json", by_alias=True)
    assert data["createdAt"] == "2026-11-04T02:00:00Z"
    assert isinstance(data["result"]["reportId"], str)
    with pytest.raises(ValidationError):
        RunView.model_validate(run() | {"finishedAt": "2026-11-03T00:00:00Z"})


@pytest.mark.parametrize(
    "field", ["stepCount", "maxSteps", "rawChecks", "hiddenPrompt", "terminalReason"]
)
def test_run_rejects_internal_fields(field):
    with pytest.raises(ValidationError):
        RunView.model_validate(run() | {field: "internal"})
    with pytest.raises(ValidationError):
        RunView.model_validate(run() | {"result": {field: "internal"}})
    with pytest.raises(ValidationError):
        RunView[ReportRunResult].model_validate(
            run() | {"result": {"reportId": str(uuid4()), field: "internal"}}
        )


def test_run_error_does_not_expose_diagnostics():
    with pytest.raises(ValidationError):
        RunView.model_validate(
            run()
            | {
                "error": {
                    "code": "FAILED",
                    "message": "稍后重试",
                    "retryable": True,
                    "traceback": "internal",
                }
            }
        )


def test_report_signals_unique_and_quote_whitespace_preserved():
    signal = dict(messageId=str(uuid4()), quote="  学生原话  ", tags=["judgment"])
    content = ReportContent.model_validate(report() | {"signals": [signal]})
    assert content.signals[0].quote == signal["quote"]
    with pytest.raises(ValidationError):
        ReportContent.model_validate(report() | {"signals": [signal, signal]})
    for patch in ({"tags": ["judgment", "judgment"]}, {"tags": ["made_up"]}, {"quote": " "}):
        with pytest.raises(ValidationError):
            ReportSignal.model_validate(signal | patch)


def test_report_finding_requires_references_and_change_needs_two_messages():
    finding = dict(kind="student_judgment", text="判断", messageIds=[], evidenceIds=[])
    with pytest.raises(ValidationError):
        ReportFinding.model_validate(finding)
    message = str(uuid4())
    with pytest.raises(ValidationError):
        ReportFinding.model_validate(
            finding | {"kind": "view_change", "messageIds": [message, message]}
        )
    ReportFinding.model_validate(
        finding | {"kind": "view_change", "messageIds": [message, str(uuid4())]}
    )
    with pytest.raises(ValidationError):
        ReportContent.model_validate(report() | {"metrics": {"expressionCount": 100}})


def test_metrics_preserve_unknown_not_zero():
    data = dict(
        expressionCount=0,
        evidenceSeekingCount=None,
        sourceViewCount=None,
        judgmentCount=None,
        reflectionCount=None,
    )
    assert ReportMetrics.model_validate(data).model_dump(by_alias=True) == data
    for invalid in (-1, True, 1.2, "1"):
        with pytest.raises(ValidationError):
            ReportMetrics.model_validate(data | {"expressionCount": invalid})


def test_pagination_and_scope_constraints():
    assert PaginationParams().limit == 20
    for invalid in (0, 101, True):
        with pytest.raises(ValidationError):
            PaginationParams(limit=invalid)
    assert Page[RoleCard](items=[], next_cursor=None).model_dump(by_alias=True) == {
        "items": [],
        "nextCursor": None,
    }
    assert ReportScope().scope == "latest"
    for data in ({"scope": "version"}, {"scope": "all", "versionId": str(uuid4())}):
        with pytest.raises(ValidationError):
            ReportScope.model_validate(data)


def test_readiness_is_a_public_shape_not_internal_check_results():
    data = dict(
        ready=True,
        state="ready",
        revision=1,
        taskRevision=1,
        contentHash="a" * 64,
        blockingIssues=[],
        nextQuestions=[],
    )
    PublishReadiness.model_validate(data)
    for patch in ({"state": "preparing"}, {"nextQuestions": ["补充？"]}, {"checks": []}):
        with pytest.raises(ValidationError):
            PublishReadiness.model_validate(data | patch)


def test_public_schemas_can_be_registered_without_routes():
    _, document = models_json_schema(
        [(model, "validation") for model in PUBLIC_SCHEMAS],
        by_alias=True,
        ref_template="#/components/schemas/{model}",
    )
    schemas = document["$defs"]
    assert schemas["TaskBrief"]["additionalProperties"] is False
    assert "topicName" in schemas["TaskBrief"]["properties"]
    assert "roleId" not in schemas["RoleCardInput"]["properties"]
    assert schemas["RoleCard"]["properties"]["roleId"]["format"] == "uuid"
    assert "stepCount" not in schemas["RunView"]["properties"]

    def check_refs(node):
        if isinstance(node, dict):
            if "$ref" in node:
                assert node["$ref"].startswith("#/components/schemas/")
                assert node["$ref"].split("/")[-1] in schemas
            for value in node.values():
                check_refs(value)
        elif isinstance(node, list):
            for value in node:
                check_refs(value)

    check_refs(schemas)
