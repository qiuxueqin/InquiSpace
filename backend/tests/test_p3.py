from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlmodel import Session, select

from app import seed
from app.core.config import BACKEND_DIR, Settings
from app.db.models import (
    AgentRun,
    Confirmation,
    ReviewRecord,
    RoleCard,
    RunStep,
    TaskVersion,
    User,
)
from app.db.session import create_db_engine
from app.integrations.deepseek_model import DeepSeekStructuredModel
from app.integrations.model import ModelAdapterError
from app.main import create_app
from app.schemas.model_outputs import (
    GeneratedPlan,
    PreflightOutput,
    RoleCandidate,
    RoleValidationOutput,
)
from app.services import p3


class FakeModel:
    model_id = "test-model"

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.prompts: list[str] = []

    def generate(self, *, system: str, prompt: str, schema):
        self.prompts.append(prompt)
        value = self.outputs.pop(0)
        if isinstance(value, ModelAdapterError):
            raise value
        assert isinstance(value, schema)
        return value


@pytest.fixture
def app_and_passwords(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("INQUISPACE_DATA_DIR", str(tmp_path))
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    settings = Settings(_env_file=None, environment="test", data_dir=tmp_path)
    passwords = {username: f"safe-{username}-password" for username, _, _ in seed.ACCOUNTS}
    engine = create_db_engine(settings)
    try:
        assert seed.seed_accounts(engine, passwords.__getitem__) == 3
    finally:
        engine.dispose()
    return create_app(settings), passwords, settings


def login(client: TestClient, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "teacher", "password": password},
        headers={"Origin": "http://testserver"},
    )
    return response.json()["data"]["csrfToken"]


def headers(csrf: str, revision: int, *, key: str | None = None) -> dict[str, str]:
    result = {
        "Origin": "http://testserver",
        "X-CSRF-Token": csrf,
        "If-Match": f'"rev-{revision}"',
    }
    if key:
        result["Idempotency-Key"] = key
    return result


def create_draft(client: TestClient, csrf: str, intent: str = "探究辛亥革命后的身份变化") -> str:
    response = client.post(
        "/api/v1/tasks",
        json={"teachingIntent": intent},
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf,
            "Idempotency-Key": "p3-task",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["draft"]["id"]


def role_input(name: str = "溥仪") -> dict[str, object]:
    return {
        "name": name,
        "roleType": "real_historical",
        "identityDescription": "清朝末代皇帝，在特定历史时点参与对话。",
        "historicalPeriod": "1912年",
        "timeAnchor": {"value": "1912", "precision": "year"},
        "region": "中国",
        "socialGroup": "清皇室",
        "position": "退位后的前皇帝",
        "goals": ["理解自身处境"],
        "concerns": ["身份与权力变化"],
        "relationships": [],
        "knownFacts": [],
        "unknownFacts": ["1912年之后的事件"],
        "sourceIds": [],
        "disputedClaims": [],
        "speechStyle": "克制并说明认知边界",
        "openingMessage": "你想从哪一方面了解我的处境？",
        "recommendedQuestions": ["退位后你的身份发生了什么变化？"],
        "learningDimension": "历史身份与制度变化",
        "forbiddenBehaviors": ["不编造", "不越界", "不代写学生结论"],
    }


def generated_plan() -> GeneratedPlan:
    return GeneratedPlan.model_validate(
        {
            "brief": {
                "topicName": "清朝灭亡后的身份变化",
                "background": "探究1912年前后制度与个人身份的变化。",
                "subject": "历史",
                "grade": "高中",
                "learningGoals": ["依据史料分析身份变化"],
                "coreQuestion": "制度变化如何影响个人身份？",
                "isHistoricalTopic": True,
                "timeAnchor": {"value": "1912", "precision": "year"},
                "region": "中国",
                "roleType": "real_historical",
                "roleName": "溥仪",
                "materialPolicy": {
                    "externalKnowledgeAllowed": False,
                    "externalKnowledgeScope": "",
                },
                "restrictions": {
                    "maxTurns": 20,
                    "suggestedMinutes": 45,
                    "deadlineAt": None,
                    "difficulty": "高中",
                    "forbiddenContent": [],
                },
                "expectedOutcome": "形成有依据的历史解释",
                "confirmedFields": [],
            },
            "roleCard": role_input(),
            "questionPlan": [
                {
                    "question": "退位如何改变角色身份？",
                    "dimension": "制度与身份",
                    "purpose": "联系制度变化与个人处境",
                }
            ],
            "assumptions": ["使用默认课时"],
            "missingFields": [],
            "nextQuestions": [],
        }
    )


def valid_checks() -> PreflightOutput:
    return PreflightOutput.model_validate(
        {
            "checks": [
                {"category": category, "result": "pass", "reason": "未发现阻断问题"}
                for category in (
                    "identity",
                    "future_information",
                    "private_motives",
                    "viewpoint_conflict",
                    "prompt_injection",
                )
            ]
        }
    )


def incomplete_historical_plan() -> GeneratedPlan:
    value = generated_plan().model_dump(by_alias=True, mode="json")
    value["brief"]["timeAnchor"] = None
    value["roleCard"] = None
    value["questionPlan"] = []
    value["missingFields"] = ["timeAnchor"]
    value["nextQuestions"] = ["希望角色处于达尔文研究过程中的哪个年份？"]
    return GeneratedPlan.model_validate(value)


def test_generated_role_sources_include_all_ready_materials():
    source_id = "10000000-0000-0000-0000-000000000001"
    other_source_id = "10000000-0000-0000-0000-000000000002"
    evidence_id = "20000000-0000-0000-0000-000000000001"
    role = role_input()
    role["knownFacts"] = [
        {"text": "有依据的事实", "evidenceIds": [evidence_id], "origin": "material"}
    ]
    bound = p3._bind_role_sources(
        role,
        [{"id": evidence_id, "sourceId": source_id}],
        {source_id, other_source_id},
    )
    assert bound is not None
    assert bound["sourceIds"] == [source_id, other_source_id]


def test_generated_role_rejects_out_of_snapshot_references():
    role = role_input()
    role["knownFacts"] = [
        {
            "text": "越界事实",
            "evidenceIds": ["20000000-0000-0000-0000-000000000002"],
            "origin": "material",
        }
    ]
    with pytest.raises(ModelAdapterError) as caught:
        p3._bind_role_sources(role, [])
    assert caught.value.code == "MODEL_INVALID_RESPONSE"
    assert caught.value.retryable is True


def test_generated_plan_rejects_optional_evidence_as_missing_field():
    value = incomplete_historical_plan().model_dump(by_alias=True, mode="json")
    value["missingFields"] = ["evidence"]
    with pytest.raises(ValidationError):
        GeneratedPlan.model_validate(value)


def test_plan_generation_validation_preflight_and_undo(app_and_passwords, monkeypatch):
    app, passwords, settings = app_and_passwords
    model = FakeModel(
        [
            generated_plan(),
            RoleValidationOutput(passed=True, issues=[]),
            valid_checks(),
        ]
    )
    monkeypatch.setattr("app.api.routes.p3.create_model", lambda _settings: model)
    with TestClient(app) as client:
        csrf = login(client, passwords["teacher"])
        version_id = create_draft(client, csrf, "探究1912年辛亥革命后的身份变化")
        started = client.post(
            f"/api/v1/versions/{version_id}/plan-generations",
            json={},
            headers=headers(csrf, 1, key="plan-generate-1"),
        )
        replay = client.post(
            f"/api/v1/versions/{version_id}/plan-generations",
            json={},
            headers=headers(csrf, 1, key="plan-generate-1"),
        )
        assert replay.status_code == 202
        assert replay.json()["data"]["id"] == started.json()["data"]["id"]
        assert started.status_code == 202, started.text
        run_id = started.json()["data"]["id"]
        run = client.get(f"/api/v1/runs/{run_id}").json()["data"]
        assert run["status"] == "completed"
        assert run["result"]["undoAvailable"] is True
        version = client.get(f"/api/v1/versions/{version_id}").json()["data"]
        assert version["revision"] == 2
        assert version["roleCard"]["name"] == "溥仪"
        assert version["generationMeta"]["appliedRunId"] == run_id

        validated = client.post(
            f"/api/v1/versions/{version_id}/validations",
            json={},
            headers=headers(csrf, 2, key="validate-1"),
        )
        validation_run = client.get(f"/api/v1/runs/{validated.json()['data']['id']}").json()["data"]
        assert validation_run["result"]["valid"] is True
        assert client.get(f"/api/v1/versions/{version_id}").json()["data"]["validatedRevision"] == 2

        preflight = client.post(
            f"/api/v1/versions/{version_id}/preflights",
            json={},
            headers=headers(csrf, 2, key="preflight-1"),
        )
        preflight_run = client.get(f"/api/v1/runs/{preflight.json()['data']['id']}").json()["data"]
        assert preflight_run["result"]["ready"] is True
        readiness = client.get(f"/api/v1/versions/{version_id}/publish-check")
        assert readiness.json()["data"]["state"] == "ready"

        undone = client.post(
            f"/api/v1/versions/{version_id}/plan-generations/{run_id}/undo",
            json={},
            headers=headers(csrf, 2, key="undo-1"),
        )
        assert undone.status_code == 200, undone.text
        assert undone.json()["data"]["revision"] == 3
        assert undone.json()["data"]["roleCard"] is None
        assert undone.json()["data"]["teachingIntent"] == "探究1912年辛亥革命后的身份变化"
        assert (
            client.post(
                f"/api/v1/versions/{version_id}/plan-generations/{run_id}/undo",
                json={},
                headers=headers(csrf, 3, key="undo-2"),
            ).json()["error"]["code"]
            == "UNDO_NOT_AVAILABLE"
        )

    with Session(app.state.engine) as session:
        stored_run = session.get(AgentRun, run_id)
        assert stored_run is not None and stored_run.step_count == 1
        assert session.exec(select(RunStep).where(RunStep.run_id == run_id)).first() is not None
        audits = session.exec(
            select(ReviewRecord).where(
                ReviewRecord.version_id == version_id,
                ReviewRecord.kind == "business_audit",
            )
        ).all()
        assert len(audits) == 2


def supported_month_anchor_plan() -> GeneratedPlan:
    value = generated_plan().model_dump(by_alias=True, mode="json")
    value["brief"]["timeAnchor"] = {"value": "1912-02", "precision": "month"}
    value["roleCard"]["historicalPeriod"] = "1912年2月"
    value["roleCard"]["timeAnchor"] = {"value": "1912-02", "precision": "month"}
    return GeneratedPlan.model_validate(value)


def unsupported_anchor_plan() -> GeneratedPlan:
    value = generated_plan().model_dump(by_alias=True, mode="json")
    value["brief"]["topicName"] = "达尔文研究进化论的过程"
    value["brief"]["roleName"] = "查尔斯·达尔文"
    value["brief"]["timeAnchor"] = {"value": "1859", "precision": "year"}
    value["roleCard"]["name"] = "查尔斯·达尔文"
    value["roleCard"]["timeAnchor"] = {"value": "1859", "precision": "year"}
    value["missingFields"] = ["region"]
    value["nextQuestions"] = ["希望限定在哪个地区？"]
    return GeneratedPlan.model_validate(value)


def test_chinese_month_in_intent_supports_iso_month_anchor(app_and_passwords, monkeypatch):
    app, passwords, _ = app_and_passwords
    model = FakeModel([supported_month_anchor_plan()])
    monkeypatch.setattr("app.api.routes.p3.create_model", lambda _settings: model)
    with TestClient(app) as client:
        csrf = login(client, passwords["teacher"])
        version_id = create_draft(
            client,
            csrf,
            "让八年级学生与1912年2月退位不久的溥仪对话，探究制度变化。",
        )
        started = client.post(
            f"/api/v1/versions/{version_id}/plan-generations",
            json={},
            headers=headers(csrf, 1, key="plan-generate-chinese-month-anchor"),
        )
        assert started.status_code == 202, started.text
        run = client.get(f"/api/v1/runs/{started.json()['data']['id']}").json()["data"]
        assert run["status"] == "completed"
        assert run["result"]["missingFields"] == []
        version = client.get(f"/api/v1/versions/{version_id}").json()["data"]
        assert version["brief"]["timeAnchor"] == {
            "value": "1912-02",
            "precision": "month",
        }
        assert version["roleCard"]["name"] == "溥仪"
        assert version["questionPlan"]


@pytest.mark.parametrize(
    ("text", "anchor"),
    [
        ("1912 年 2 月清帝退位", "1912-02"),
        ("1859年11月《物种起源》首版刚出版", "1859-11"),
        ("时间为1912年02月12日", "1912-02-12"),
        ("时间为1912年2月12号", "1912-02-12"),
        ("研究1859年的科学讨论", "1859"),
    ],
)
def test_anchor_text_formats_are_equivalent(text: str, anchor: str):
    assert p3._text_supports_anchor(text, anchor)


def test_month_anchor_requires_month_not_only_year():
    assert not p3._text_supports_anchor("研究1912年的制度变化", "1912-02")


def test_incomplete_historical_plan_is_saved_as_safe_draft(app_and_passwords, monkeypatch):
    app, passwords, _ = app_and_passwords
    model = FakeModel([incomplete_historical_plan()])
    monkeypatch.setattr("app.api.routes.p3.create_model", lambda _settings: model)
    with TestClient(app) as client:
        csrf = login(client, passwords["teacher"])
        version_id = create_draft(client, csrf, "让九年级学生理解达尔文研究进化论的过程")
        started = client.post(
            f"/api/v1/versions/{version_id}/plan-generations",
            json={},
            headers=headers(csrf, 1, key="plan-generate-incomplete"),
        )
        assert started.status_code == 202, started.text
        run = client.get(f"/api/v1/runs/{started.json()['data']['id']}").json()["data"]
        assert run["status"] == "completed"
        assert run["result"]["missingFields"] == ["timeAnchor"]
        version = client.get(f"/api/v1/versions/{version_id}").json()["data"]
        assert version["revision"] == 2
        assert version["brief"]["timeAnchor"] is None
        assert version["roleCard"] is None
        assert version["questionPlan"] == []
        assert version["generationMeta"]["missingFields"] == ["timeAnchor"]
        assert version["missingFields"] == ["timeAnchor"]
        assert version["nextQuestions"] == ["希望角色处于达尔文研究过程中的哪个年份？"]


def test_historical_null_anchor_without_missing_marker_is_normalized(
    app_and_passwords, monkeypatch
):
    app, passwords, _ = app_and_passwords
    value = incomplete_historical_plan().model_dump(by_alias=True, mode="json")
    value["missingFields"] = ["region"]
    value["nextQuestions"] = ["希望限定在哪个地区？"]
    model = FakeModel([GeneratedPlan.model_validate(value)])
    monkeypatch.setattr("app.api.routes.p3.create_model", lambda _settings: model)
    with TestClient(app) as client:
        csrf = login(client, passwords["teacher"])
        version_id = create_draft(client, csrf, "让九年级学生理解达尔文研究进化论的过程")
        started = client.post(
            f"/api/v1/versions/{version_id}/plan-generations",
            json={},
            headers=headers(csrf, 1, key="plan-generate-null-anchor"),
        )
        run = client.get(f"/api/v1/runs/{started.json()['data']['id']}").json()["data"]
        assert run["status"] == "completed"
        assert run["result"]["missingFields"][:2] == ["timeAnchor", "region"]
        version = client.get(f"/api/v1/versions/{version_id}").json()["data"]
        assert version["roleCard"] is None
        assert version["questionPlan"] == []
        assert version["missingFields"][:2] == ["timeAnchor", "region"]


def test_unsupported_generated_year_is_downgraded_not_invented(app_and_passwords, monkeypatch):
    app, passwords, _ = app_and_passwords
    model = FakeModel([unsupported_anchor_plan()])
    monkeypatch.setattr("app.api.routes.p3.create_model", lambda _settings: model)
    with TestClient(app) as client:
        csrf = login(client, passwords["teacher"])
        version_id = create_draft(client, csrf, "让九年级学生理解达尔文研究进化论的过程")
        started = client.post(
            f"/api/v1/versions/{version_id}/plan-generations",
            json={},
            headers=headers(csrf, 1, key="plan-generate-unsupported-anchor"),
        )
        run = client.get(f"/api/v1/runs/{started.json()['data']['id']}").json()["data"]
        assert run["status"] == "completed"
        assert run["result"]["missingFields"][0] == "timeAnchor"
        version = client.get(f"/api/v1/versions/{version_id}").json()["data"]
        assert version["brief"]["timeAnchor"] is None
        assert version["roleCard"] is None
        assert version["questionPlan"] == []
        assert "哪个年份" in version["nextQuestions"][0]


def test_plan_generation_retries_retryable_model_output(app_and_passwords, monkeypatch):
    app, passwords, _ = app_and_passwords
    model = FakeModel(
        [
            ModelAdapterError("MODEL_INVALID_RESPONSE", "模型返回内容不符合要求", retryable=True),
            generated_plan(),
        ]
    )
    monkeypatch.setattr("app.api.routes.p3.create_model", lambda _settings: model)
    with TestClient(app) as client:
        csrf = login(client, passwords["teacher"])
        version_id = create_draft(client, csrf)
        started = client.post(
            f"/api/v1/versions/{version_id}/plan-generations",
            json={},
            headers=headers(csrf, 1, key="plan-generate-retry"),
        )
        assert started.status_code == 202, started.text
        run_id = started.json()["data"]["id"]
        run = client.get(f"/api/v1/runs/{run_id}").json()["data"]
        assert run["status"] == "completed"
        assert client.get(f"/api/v1/versions/{version_id}").json()["data"]["revision"] == 2

    with Session(app.state.engine) as session:
        stored = session.get(AgentRun, run_id)
        steps = session.exec(
            select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.step_no)
        ).all()
        assert stored is not None and stored.step_count == 2
        assert [(step.status, step.attempt) for step in steps] == [
            ("failed", 1),
            ("completed", 2),
        ]


def test_plan_generation_stops_after_three_retryable_failures(app_and_passwords, monkeypatch):
    app, passwords, _ = app_and_passwords
    model = FakeModel(
        [
            ModelAdapterError("MODEL_INVALID_RESPONSE", "模型返回内容不符合要求", retryable=True)
            for _ in range(3)
        ]
    )
    monkeypatch.setattr("app.api.routes.p3.create_model", lambda _settings: model)
    with TestClient(app) as client:
        csrf = login(client, passwords["teacher"])
        version_id = create_draft(client, csrf)
        started = client.post(
            f"/api/v1/versions/{version_id}/plan-generations",
            json={},
            headers=headers(csrf, 1, key="plan-generate-fail"),
        )
        run_id = started.json()["data"]["id"]
        run = client.get(f"/api/v1/runs/{run_id}").json()["data"]
        assert run["status"] == "failed"
        assert run["error"] == {
            "code": "MODEL_INVALID_RESPONSE",
            "message": "模型返回内容不符合要求",
            "retryable": True,
        }
        assert client.get(f"/api/v1/versions/{version_id}").json()["data"]["revision"] == 1

    with Session(app.state.engine) as session:
        stored = session.get(AgentRun, run_id)
        steps = session.exec(
            select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.step_no)
        ).all()
        assert stored is not None and stored.step_count == 3
        assert [step.attempt for step in steps] == [1, 2, 3]
        assert all(step.status == "failed" for step in steps)


def test_role_candidate_requires_bound_confirmation(app_and_passwords, monkeypatch):
    app, passwords, _ = app_and_passwords
    candidate = RoleCandidate.model_validate(
        {
            "roleCard": role_input("虚拟报人"),
            "recommendationReason": "适合讨论身份转型",
            "questionPlan": [
                {"question": "你如何理解变化？", "dimension": "身份", "purpose": "提出解释"}
            ],
            "coverage": {"coveredGoals": [], "gaps": [], "disputes": [], "risks": []},
        }
    )
    model = FakeModel([candidate])
    monkeypatch.setattr("app.api.routes.p3.create_model", lambda _settings: model)
    with TestClient(app) as client:
        csrf = login(client, passwords["teacher"])
        version_id = create_draft(client, csrf, "生成一个历史角色")
        started = client.post(
            f"/api/v1/versions/{version_id}/role-generations",
            json={},
            headers=headers(csrf, 1, key="role-generate-1"),
        )
        run_id = started.json()["data"]["id"]
        run = client.get(f"/api/v1/runs/{run_id}").json()["data"]
        assert run["status"] == "waiting_confirmation"
        candidate_hash = run["result"]["candidateHash"]
        denied = client.post(
            f"/api/v1/versions/{version_id}/role-candidates/{run_id}/apply",
            json={"confirmationId": "missing"},
            headers=headers(csrf, 1, key="apply-missing"),
        )
        assert denied.json()["error"]["code"] == "CONFIRMATION_REQUIRED"
        confirmation = client.post(
            f"/api/v1/versions/{version_id}/confirmations",
            json={
                "action": "apply_role_candidate",
                "confirmed": True,
                "taskRevision": 1,
                "payload": {"runId": run_id, "candidateHash": candidate_hash},
            },
            headers=headers(csrf, 1, key="confirm-candidate"),
        )
        assert confirmation.status_code == 201, confirmation.text
        confirmation_id = confirmation.json()["data"]["confirmationId"]
        applied = client.post(
            f"/api/v1/versions/{version_id}/role-candidates/{run_id}/apply",
            json={"confirmationId": confirmation_id},
            headers=headers(csrf, 1, key="apply-candidate"),
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["data"]["revision"] == 2
        assert applied.json()["data"]["roleCard"]["name"] == "虚拟报人"
    with Session(app.state.engine) as session:
        confirmation_row = session.get(Confirmation, confirmation_id)
        assert confirmation_row is not None and confirmation_row.consumed_at is not None


def test_manual_role_mismatch_is_invalid_and_stale_run_does_not_overwrite(
    app_and_passwords, monkeypatch
):
    app, passwords, settings = app_and_passwords
    with TestClient(app) as client:
        csrf = login(client, passwords["teacher"])
        version_id = create_draft(client, csrf)
        saved = client.put(
            f"/api/v1/versions/{version_id}/role-card",
            json={"roleCard": role_input("不一致角色")},
            headers=headers(csrf, 1),
        )
        assert saved.status_code == 200
        assert client.get(f"/api/v1/versions/{version_id}").json()["data"]["validationStatus"] in {
            "stale",
            "invalid",
        }

    # Exercise stale write protection directly to control the race deterministically.
    from app.services import p3

    with Session(app.state.engine) as session:
        user = session.exec(select(User).where(User.username == "teacher")).first()
        version = session.get(TaskVersion, version_id)
        version.manual_fields_json = "[]"
        session.commit()
        run = p3.start_plan_generation(
            session,
            user,
            version_id,
            expected_revision=2,
            confirmation_id=None,
            settings=settings,
        )
        run_id = run.id
        version = session.get(TaskVersion, version_id)
        version.revision = 3
        session.commit()
    p3.process_plan_generation(app.state.engine, settings, FakeModel([generated_plan()]), run_id)
    with Session(app.state.engine) as session:
        stale = session.get(AgentRun, run_id)
        version = session.get(TaskVersion, version_id)
        card = session.exec(select(RoleCard).where(RoleCard.version_id == version_id)).first()
        assert stale is not None and stale.terminal_reason == "STALE_REVISION"
        assert version is not None and version.revision == 3
        assert card is not None


def test_replace_plan_confirmation_binds_intent_and_manual_fields(app_and_passwords):
    app, passwords, _ = app_and_passwords
    with TestClient(app) as client:
        csrf = login(client, passwords["teacher"])
        version_id = create_draft(client, csrf)
        patched = client.patch(
            f"/api/v1/versions/{version_id}",
            json={"brief": {"topicName": "教师手工主题"}},
            headers=headers(csrf, 1),
        )
        assert patched.status_code == 200
        intent_hash = hashlib.sha256("探究辛亥革命后的身份变化".encode()).hexdigest()
        wrong = client.post(
            f"/api/v1/versions/{version_id}/confirmations",
            json={
                "action": "replace_plan",
                "confirmed": True,
                "taskRevision": 1,
                "payload": {"intentHash": intent_hash, "overwrittenFields": []},
            },
            headers=headers(csrf, 2, key="confirm-replace-wrong"),
        )
        assert wrong.json()["error"]["code"] == "CONFIRMATION_STALE"
        confirmed = client.post(
            f"/api/v1/versions/{version_id}/confirmations",
            json={
                "action": "replace_plan",
                "confirmed": True,
                "taskRevision": 1,
                "payload": {
                    "intentHash": intent_hash,
                    "overwrittenFields": ["brief.topicName"],
                },
            },
            headers=headers(csrf, 2, key="confirm-replace"),
        )
        assert confirmed.status_code == 201


def test_deepseek_adapter_sends_json_mode_and_validates_schema():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = request.read().decode()
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": generated_plan().model_dump_json(by_alias=True)},
                    }
                ]
            },
        )

    settings = Settings(
        _env_file=None,
        environment="test",
        llm_api_key="deepseek-test-key",
        llm_base_url="https://api.deepseek.com",
        llm_model="deepseek-flash",
        llm_effort="high",
    )
    adapter = DeepSeekStructuredModel(settings)
    adapter._client.close()
    adapter._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer deepseek-test-key"},
    )
    result = adapter.generate(system="生成方案", prompt="输入", schema=GeneratedPlan)

    assert result.brief.topic_name == "清朝灭亡后的身份变化"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["authorization"] == "Bearer deepseek-test-key"
    body = json.loads(captured["body"])
    assert body["model"] == "deepseek-flash"
    assert body["reasoning_effort"] == "high"
    assert body["response_format"] == {"type": "json_object"}
    assert "JSON Schema" in body["messages"][1]["content"]
    assert "目标 JSON 示例" in body["messages"][1]["content"]
    assert '"roleCard":null' in body["messages"][1]["content"]


def test_deepseek_adapter_distinguishes_invalid_json_and_schema():
    settings = Settings(_env_file=None, environment="test", llm_api_key="deepseek-test-key")
    adapter = DeepSeekStructuredModel(settings)
    adapter._client.close()
    adapter._client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"choices": [{"finish_reason": "stop", "message": {"content": "{"}}]},
            )
        )
    )
    with pytest.raises(ModelAdapterError, match="有效 JSON") as invalid_json:
        adapter.generate(system="生成方案", prompt="输入", schema=GeneratedPlan)
    assert invalid_json.value.code == "MODEL_INVALID_JSON"

    adapter._client.close()
    adapter._client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]},
            )
        )
    )
    with pytest.raises(ModelAdapterError, match="brief") as mismatch:
        adapter.generate(system="生成方案", prompt="输入", schema=GeneratedPlan)
    assert mismatch.value.code == "MODEL_SCHEMA_MISMATCH"
    adapter._client.close()


def test_deepseek_adapter_maps_timeout_and_truncation():
    settings = Settings(
        _env_file=None,
        environment="test",
        llm_api_key="deepseek-test-key",
    )
    adapter = DeepSeekStructuredModel(settings)
    adapter._client.close()
    adapter._client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
            )
        )
    )
    with pytest.raises(ModelAdapterError, match="输出不完整") as truncated:
        adapter.generate(system="生成方案", prompt="输入", schema=GeneratedPlan)
    assert truncated.value.code == "MODEL_OUTPUT_INCOMPLETE"

    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    adapter._client.close()
    adapter._client = httpx.Client(transport=httpx.MockTransport(timeout))
    with pytest.raises(ModelAdapterError, match="响应超时") as timed_out:
        adapter.generate(system="生成方案", prompt="输入", schema=GeneratedPlan)
    assert timed_out.value.code == "MODEL_TIMEOUT"


def test_deepseek_adapter_requires_backend_key():
    settings = Settings(_env_file=None, environment="test", llm_api_key=None)
    with pytest.raises(ModelAdapterError, match="DeepSeek API 密钥") as missing:
        DeepSeekStructuredModel(settings)
    assert missing.value.code == "MODEL_CONFIGURATION_ERROR"
