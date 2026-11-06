"""P4 dialogue workflow and API tests."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import seed
from app.core.config import BACKEND_DIR, Settings
from app.db.models import (
    AgentRun,
    Citation,
    Evidence,
    Message,
    ReviewRecord,
    RoleCard,
    RoleSession,
    RunEvent,
    Source,
    Task,
    TaskMember,
    TaskVersion,
    User,
    VersionSource,
)
from app.db.session import create_db_engine
from app.integrations.deepseek_model import DeepSeekStructuredModel
from app.integrations.model import ModelAdapterError
from app.main import create_app
from app.schemas.model_outputs import (
    AnswerCheckOutput,
    ConversationSummaryOutput,
    FollowUpOutput,
)
from app.services import dialogue
from app.workflows.runtime import WorkflowRuntime


class FakeDialogueModel:
    model_id = "test-dialogue"

    def __init__(self, lines: list[str], checks=None, summary=None):
        self.lines = lines
        self.checks = list(checks or [])
        self.summary = summary

    def stream_text(self, *, system: str, prompt: str, cancel=None):
        value = "\n".join(self.lines) + "\n"
        midpoint = len(value) // 2
        yield value[:midpoint]
        yield value[midpoint:]

    def generate(self, *, system: str, prompt: str, schema):
        if schema is AnswerCheckOutput:
            if self.checks:
                return self.checks.pop(0)
            return AnswerCheckOutput(passed=True, issues=[])
        if schema is FollowUpOutput:
            return FollowUpOutput(follow_up_questions=["你还想核对哪一项依据？"])
        if schema is ConversationSummaryOutput:
            return self.summary or ConversationSummaryOutput(
                student_views=["学生提出了身份变化问题"],
                verified_facts=[],
                unresolved_questions=["变化的具体依据是什么？"],
                prior_follow_ups=[],
            )
        raise AssertionError(schema)


@pytest.fixture
def p4_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("INQUISPACE_DATA_DIR", str(tmp_path))
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    settings = Settings(_env_file=None, environment="test", data_dir=tmp_path)
    passwords = {username: f"safe-{username}-password" for username, _, _ in seed.ACCOUNTS}
    engine = create_db_engine(settings)
    try:
        seed.seed_accounts(engine, passwords.__getitem__)
        with Session(engine) as session:
            teacher = session.exec(select(User).where(User.username == "teacher")).one()
            student1 = session.exec(select(User).where(User.username == "student1")).one()
            now = dialogue._now()
            task = Task(
                id="10000000-0000-0000-0000-000000000001",
                owner_id=teacher.id,
                status="active",
                row_version=1,
                current_published_version_id=None,
                archived_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(task)
            session.flush()
            brief = {
                "topicName": "身份变化",
                "background": "探究制度变化",
                "subject": "历史",
                "grade": "八年级",
                "learningGoals": ["依据材料解释变化"],
                "coreQuestion": "身份如何变化？",
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
                    "difficulty": "八年级",
                    "forbiddenContent": [],
                },
                "expectedOutcome": "形成有依据的解释",
                "confirmedFields": [],
            }
            version = TaskVersion(
                id="20000000-0000-0000-0000-000000000001",
                task_id=task.id,
                version_no=1,
                revision=1,
                status="published",
                from_version_id=None,
                teaching_intent="探究身份变化",
                manual_fields_json="[]",
                generation_meta_json="{}",
                brief_json=json.dumps(brief, ensure_ascii=False),
                question_plan_json=json.dumps(
                    [{"question": "身份如何变化？", "dimension": "身份", "purpose": "解释"}],
                    ensure_ascii=False,
                ),
                validation_status="valid",
                validated_revision=1,
                preview_revision=1,
                content_hash="a" * 64,
                published_at=now,
                published_by=teacher.id,
                created_at=now,
                updated_at=now,
            )
            session.add(version)
            session.flush()
            task.current_published_version_id = version.id
            card = {
                "name": "溥仪",
                "roleType": "real_historical",
                "identityDescription": "清朝末代皇帝",
                "historicalPeriod": "1912年",
                "timeAnchor": {"value": "1912", "precision": "year"},
                "region": "中国",
                "socialGroup": "清皇室",
                "position": "退位后的前皇帝",
                "goals": [],
                "concerns": [],
                "relationships": [],
                "knownFacts": [],
                "unknownFacts": ["1912年后的事件"],
                "sourceIds": [],
                "disputedClaims": [],
                "speechStyle": "克制",
                "openingMessage": "你想了解什么？",
                "recommendedQuestions": ["身份发生了什么变化？"],
                "learningDimension": "身份变化",
                "forbiddenBehaviors": ["不编造", "不越界", "不代写"],
            }
            session.add(
                RoleCard(
                    id="30000000-0000-0000-0000-000000000001",
                    version_id=version.id,
                    card_json=json.dumps(card, ensure_ascii=False),
                    edited_by=teacher.id,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                TaskMember(
                    task_id=task.id, user_id=student1.id, granted_by=teacher.id, created_at=now
                )
            )
            session.commit()
    finally:
        engine.dispose()
    app = create_app(settings)
    model = FakeDialogueModel(
        [
            json.dumps(
                {"type": "unknown", "text": "现有资料无法确认。", "evidenceIds": []},
                ensure_ascii=False,
            )
        ]
    )
    monkeypatch.setattr("app.api.routes.dialogue.create_model", lambda _settings: model)
    monkeypatch.setattr("app.api.routes.runs.create_model", lambda _settings: model)
    return app, passwords, settings, model


def login(client: TestClient, username: str, password: str):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200
    return response.json()["data"]["csrfToken"]


def write_headers(csrf: str, key: str):
    return {"Origin": "http://testserver", "X-CSRF-Token": csrf, "Idempotency-Key": key}


def test_student_session_chat_messages_summary_and_sse(p4_env):
    app, passwords, _, _ = p4_env
    with TestClient(app) as client:
        csrf = login(client, "student1", passwords["student1"])
        created = client.post(
            "/api/v1/tasks/10000000-0000-0000-0000-000000000001/sessions",
            json={},
            headers=write_headers(csrf, "student-session"),
        )
        assert created.status_code == 201, created.text
        role_session = created.json()["data"]
        assert role_session["publicRole"]["name"] == "溥仪"
        assert "knownFacts" not in role_session["publicRole"]
        session_id = role_session["id"]

        sent = client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"content": "你的身份发生了什么变化？"},
            headers=write_headers(csrf, "message-one"),
        )
        assert sent.status_code == 202, sent.text
        run_id = sent.json()["data"]["runId"]
        run = client.get(f"/api/v1/runs/{run_id}").json()["data"]
        assert run["status"] == "completed"
        messages = client.get(f"/api/v1/sessions/{session_id}/messages").json()["data"]
        assert [item["speaker"] for item in messages["items"]] == ["user", "assistant"]
        assert messages["items"][1]["status"] == "complete"
        assert messages["items"][1]["blocks"][0]["type"] == "unknown"
        assert messages["items"][1]["meta"]["followUpQuestions"]
        events = client.get(f"/api/v1/runs/{run_id}/events?afterSeq=0")
        assert "event: answer.block" in events.text
        assert "event: answer.meta" in events.text
        assert "event: run.completed" in events.text

        summary = client.post(
            f"/api/v1/sessions/{session_id}/summaries",
            json={},
            headers=write_headers(csrf, "summary-one"),
        )
        assert summary.status_code == 202
        summary_run = client.get(f"/api/v1/runs/{summary.json()['data']['id']}").json()["data"]
        assert summary_run["status"] == "completed"
        assert summary_run["result"]["unresolvedQuestions"]
        latest = client.get(f"/api/v1/sessions/{session_id}").json()["data"]
        assert latest["completedTurns"] == 1
        assert latest["summary"]["studentViews"]

    with Session(app.state.engine) as session:
        run = session.get(AgentRun, run_id)
        assert run.step_count == 3
        assert session.exec(select(ReviewRecord).where(ReviewRecord.run_id == run_id)).first()
        assert session.exec(select(RunEvent).where(RunEvent.run_id == run_id)).all()


def test_cross_student_access_is_hidden(p4_env):
    app, passwords, _, _ = p4_env
    with TestClient(app) as client:
        csrf = login(client, "student1", passwords["student1"])
        created = client.post(
            "/api/v1/tasks/10000000-0000-0000-0000-000000000001/sessions",
            json={},
            headers=write_headers(csrf, "student-session-two"),
        )
        session_id = created.json()["data"]["id"]
        sent = client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"content": "权限检查问题"},
            headers=write_headers(csrf, "student-message-two"),
        )
        run_id = sent.json()["data"]["runId"]
        client.post(
            "/api/v1/auth/logout",
            json={},
            headers={
                "Origin": "http://testserver",
                "X-CSRF-Token": csrf,
            },
        )
        login(client, "student2", passwords["student2"])
        assert client.get(f"/api/v1/sessions/{session_id}").status_code == 404
        assert client.get(f"/api/v1/sessions/{session_id}/messages").status_code == 404
        assert client.get(f"/api/v1/runs/{run_id}").status_code == 404
        assert client.get(f"/api/v1/runs/{run_id}/events?afterSeq=0").status_code == 404
        assert client.get(f"/api/v1/sessions/{session_id}/learning-report").status_code == 404
        assert client.get(f"/api/v1/sessions/{session_id}/notes").status_code == 404


def test_failed_chat_can_retry_and_does_not_increment_turn(p4_env, monkeypatch):
    app, passwords, settings, _ = p4_env
    failing = FakeDialogueModel(["not-json"])
    monkeypatch.setattr("app.api.routes.dialogue.create_model", lambda _settings: failing)
    with TestClient(app) as client:
        csrf = login(client, "student1", passwords["student1"])
        created = client.post(
            "/api/v1/tasks/10000000-0000-0000-0000-000000000001/sessions",
            json={},
            headers=write_headers(csrf, "student-session-three"),
        )
        session_id = created.json()["data"]["id"]
        sent = client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"content": "问题"},
            headers=write_headers(csrf, "failed-message"),
        )
        run_id = sent.json()["data"]["runId"]
        failed = client.get(f"/api/v1/runs/{run_id}").json()["data"]
        assert failed["status"] == "failed"
        assert client.get(f"/api/v1/sessions/{session_id}").json()["data"]["completedTurns"] == 0

        succeeding = FakeDialogueModel(
            [
                json.dumps(
                    {"type": "unknown", "text": "我无法确认。", "evidenceIds": []},
                    ensure_ascii=False,
                )
            ]
        )
        monkeypatch.setattr("app.api.routes.runs.create_model", lambda _settings: succeeding)
        retried = client.post(
            f"/api/v1/runs/{run_id}/retry",
            json={},
            headers=write_headers(csrf, "retry-one"),
        )
        assert retried.status_code == 202, retried.text
        assert (
            client.get(f"/api/v1/runs/{retried.json()['data']['id']}").json()["data"]["status"]
            == "completed"
        )
        assert (
            client.post(
                f"/api/v1/runs/{run_id}/retry",
                json={},
                headers=write_headers(csrf, "retry-old"),
            ).status_code
            == 409
        )


def test_startup_recovery_preserves_partial_message(p4_env):
    app, _, settings, _ = p4_env
    with TestClient(app):
        with Session(app.state.engine) as session:
            student = session.exec(select(User).where(User.username == "student1")).one()
            role_session, _ = dialogue.create_student_session(
                session, student, "10000000-0000-0000-0000-000000000001"
            )
            result, _, run_id = dialogue.start_message(
                session,
                student,
                role_session.id,
                "恢复测试",
                settings,
                path=f"/api/v1/sessions/{role_session.id}/messages",
                idempotency_key="recovery-message",
            )
            run = session.get(AgentRun, run_id)
            message = session.get(Message, run.output_message_id)
            message.status = "partial"
            message.blocks_json = json.dumps(
                [{"blockIndex": 0, "type": "unknown", "text": "部分内容", "evidenceIds": []}],
                ensure_ascii=False,
            )
            message.text = "部分内容"
            session.commit()
        assert dialogue.fail_interrupted_dialogue_runs(app.state.engine) == 1
        with Session(app.state.engine) as session:
            run = session.get(AgentRun, run_id)
            message = session.get(Message, result.assistant_message_id)
            assert run.status == "failed"
            assert run.terminal_reason == "PROCESS_INTERRUPTED"
            assert message.status == "partial"


def test_legacy_student_snapshot_uses_published_ready_sources(p4_env):
    app, _, _, _ = p4_env
    source_id = "40000000-0000-0000-0000-000000000001"
    evidence_id = "50000000-0000-0000-0000-000000000001"
    with TestClient(app):
        with Session(app.state.engine) as session:
            student = session.exec(select(User).where(User.username == "student1")).one()
            role_session_view, _ = dialogue.create_student_session(
                session, student, "10000000-0000-0000-0000-000000000001"
            )
            role_session = session.get(RoleSession, role_session_view.id)
            source = Source(
                id=source_id,
                task_id=role_session.task_id,
                uploaded_by=session.exec(select(User.id).where(User.username == "teacher")).one(),
                file_name="溥仪资料.txt",
                file_type="txt",
                byte_size=100,
                sha256="b" * 64,
                storage_key=f"{role_session.task_id}/{source_id}.txt",
                status="ready",
                page_count=None,
                total_lines=1,
                parser_version="test",
                parse_error_json=None,
                warnings_json="[]",
                created_at=dialogue._now(),
                updated_at=dialogue._now(),
            )
            session.add(source)
            session.flush()
            session.add(
                VersionSource(
                    task_id=role_session.task_id,
                    version_id=role_session.version_id,
                    source_id=source.id,
                    created_at=dialogue._now(),
                )
            )
            session.add(
                Evidence(
                    id=evidence_id,
                    source_id=source.id,
                    ordinal=1,
                    text=("1908年，年幼的溥仪即皇帝位。由于他还是儿童，国家事务并非由他独立处理。"),
                    page_no=None,
                    paragraph_no=1,
                    start_line=1,
                    end_line=1,
                    disputed=0,
                    created_at=dialogue._now(),
                )
            )
            session.commit()

            rows = dialogue._candidate_evidence(session, role_session, "你在位时自己掌权吗？")

    assert [row.id for row, _source in rows] == [evidence_id]


def test_generation_prompt_prioritizes_answering_over_repeated_refusal(p4_env):
    app, _, _, _ = p4_env
    with TestClient(app):
        with Session(app.state.engine) as session:
            student = session.exec(select(User).where(User.username == "student1")).one()
            role_session_view, _ = dialogue.create_student_session(
                session, student, "10000000-0000-0000-0000-000000000001"
            )
            role_session = session.get(RoleSession, role_session_view.id)
            system, _ = dialogue._generation_prompt(
                role_session,
                "你的身份发生了什么变化？",
                [],
                [],
            )

    assert "先直接回答学生实际提出的问题" in system
    assert "不要因为证据片段为空就反复输出同义的拒答" in system
    assert "不要在结尾追加" in system
    assert "仅当学生实际追问的核心就是未知内容时" in system
    assert dialogue.PROMPT_VERSION == "p4-dialogue-v3"


def test_fact_without_candidate_evidence_fails(p4_env):
    app, _, settings, _ = p4_env
    with TestClient(app):
        with Session(app.state.engine) as session:
            student = session.exec(select(User).where(User.username == "student1")).one()
            role_session, _ = dialogue.create_student_session(
                session, student, "10000000-0000-0000-0000-000000000001"
            )
            _, _, run_id = dialogue.start_message(
                session,
                student,
                role_session.id,
                "事实是什么",
                settings,
                path=f"/api/v1/sessions/{role_session.id}/messages",
                idempotency_key="fact-message",
            )
        model = FakeDialogueModel(
            [
                json.dumps(
                    {"type": "fact", "text": "一个事实", "evidenceIds": []}, ensure_ascii=False
                )
            ]
        )
        dialogue.process_chat(app.state.engine, settings, model, WorkflowRuntime(2), run_id)
        with Session(app.state.engine) as session:
            run = session.get(AgentRun, run_id)
            message = session.get(Message, run.output_message_id)
            assert run.status == "failed"
            assert run.terminal_reason == "ANSWER_REJECTED"
            assert message.status == "discarded"
            assert (
                session.exec(select(Citation).where(Citation.message_id == message.id)).all() == []
            )


def test_deepseek_streaming_adapter_chunks_and_done():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.read())
        body = (
            'data: {"choices":[{"delta":{"content":"第一"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{"content":"段"},"finish_reason":null}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=body)

    settings = Settings(_env_file=None, environment="test", llm_api_key="test-key")
    adapter = DeepSeekStructuredModel(settings)
    adapter._client.close()
    adapter._client = httpx.Client(transport=httpx.MockTransport(handler))
    assert "".join(adapter.stream_text(system="系统", prompt="问题")) == "第一段"
    assert captured["body"]["stream"] is True
    assert "response_format" not in captured["body"]


def test_deepseek_streaming_adapter_rejects_truncated_stream():
    settings = Settings(_env_file=None, environment="test", llm_api_key="test-key")
    adapter = DeepSeekStructuredModel(settings)
    adapter._client.close()
    adapter._client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                text=(
                    'data: {"choices":[{"delta":{"content":"未完成"},"finish_reason":null}]}\n\n'
                ),
            )
        )
    )
    with pytest.raises(ModelAdapterError) as caught:
        list(adapter.stream_text(system="系统", prompt="问题"))
    assert caught.value.code == "MODEL_OUTPUT_INCOMPLETE"
