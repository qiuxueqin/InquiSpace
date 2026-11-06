"""P5 publication, automatic learning report, and teacher aggregate tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import seed
from app.core.config import BACKEND_DIR, Settings
from app.db.models import ReviewRecord, RoleCard, Task, TaskVersion, User
from app.db.session import create_db_engine
from app.main import create_app
from app.schemas.contracts import ReportContent
from app.schemas.model_outputs import AnswerCheckOutput, FollowUpOutput
from app.services import dialogue, p3


class P5Model:
    model_id = "p5-test-model"

    def stream_text(self, *, system: str, prompt: str, cancel=None):
        yield (
            json.dumps(
                {"type": "unknown", "text": "现有资料不足以确认。", "evidenceIds": []},
                ensure_ascii=False,
            )
            + "\n"
        )

    def generate(self, *, system: str, prompt: str, schema):
        if schema is AnswerCheckOutput:
            return AnswerCheckOutput(passed=True, issues=[])
        if schema is FollowUpOutput:
            return FollowUpOutput(follow_up_questions=["你还想核对什么依据？"])
        if schema is ReportContent:
            snapshot = json.loads(prompt)
            first = snapshot["studentMessages"][0]
            return ReportContent.model_validate(
                {
                    "summary": {"text": "学生提出了一个问题。", "messageIds": [first["messageId"]]},
                    "findings": [
                        {
                            "kind": "unresolved",
                            "text": "这个问题仍需更多资料。",
                            "messageIds": [first["messageId"]],
                            "evidenceIds": [],
                        }
                    ],
                    "signals": [
                        {
                            "messageId": first["messageId"],
                            "quote": first["text"],
                            "tags": ["evidence_seeking"],
                        }
                    ],
                    "missingAspects": ["尚未表达确定判断"],
                    "nextSteps": ["继续核对资料"],
                }
            )
        raise AssertionError(schema)


@pytest.fixture
def p5_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("INQUISPACE_DATA_DIR", str(tmp_path))
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    settings = Settings(_env_file=None, environment="test", data_dir=tmp_path)
    passwords = {username: f"safe-{username}-password" for username, _, _ in seed.ACCOUNTS}
    engine = create_db_engine(settings)
    try:
        seed.seed_accounts(engine, passwords.__getitem__)
        with Session(engine) as session:
            teacher = session.exec(select(User).where(User.username == "teacher")).one()
            now = dialogue._now()
            task = Task(
                id="51000000-0000-0000-0000-000000000001",
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
                id="52000000-0000-0000-0000-000000000001",
                task_id=task.id,
                version_no=1,
                revision=1,
                status="draft",
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
                content_hash=None,
                published_at=None,
                published_by=None,
                created_at=now,
                updated_at=now,
            )
            session.add(version)
            session.flush()
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
                    id="53000000-0000-0000-0000-000000000001",
                    version_id=version.id,
                    card_json=json.dumps(card, ensure_ascii=False),
                    edited_by=teacher.id,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()
            content_hash = p3.content_hash(session, version)
            session.add(
                ReviewRecord(
                    id="54000000-0000-0000-0000-000000000001",
                    task_id=task.id,
                    version_id=version.id,
                    version_revision=1,
                    kind="publish_preflight",
                    session_id=None,
                    run_id=None,
                    message_id=None,
                    block_index=None,
                    actor_id=None,
                    passed=1,
                    result_json=json.dumps(
                        {
                            "passed": True,
                            "contentHash": content_hash,
                            "checkVersion": p3.CHECK_VERSION,
                            "checks": [],
                        }
                    ),
                    issues_json="[]",
                    created_at=now,
                )
            )
            session.commit()
    finally:
        engine.dispose()
    app = create_app(settings)
    model = P5Model()
    monkeypatch.setattr("app.api.routes.dialogue.create_model", lambda _settings: model)
    monkeypatch.setattr("app.api.routes.p5.create_model", lambda _settings: model)
    return app, passwords


def login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200
    return response.json()["data"]["csrfToken"]


def write_headers(csrf: str, key: str, revision: int | None = None):
    result = {
        "Origin": "http://testserver",
        "X-CSRF-Token": csrf,
        "Idempotency-Key": key,
    }
    if revision is not None:
        result["If-Match"] = f'"rev-{revision}"'
    return result


def test_publish_student_report_correction_and_teacher_dashboard(p5_env):
    app, passwords = p5_env
    with TestClient(app) as client:
        teacher_csrf = login(client, "teacher", passwords["teacher"])
        students = client.get("/api/v1/users?role=student").json()["data"]["items"]
        student_id = students[0]["id"]
        confirmation = client.post(
            "/api/v1/versions/52000000-0000-0000-0000-000000000001/confirmations",
            json={
                "action": "publish_version",
                "confirmed": True,
                "taskRevision": 1,
                "payload": {"studentIds": [student_id]},
            },
            headers=write_headers(teacher_csrf, "publish-confirm", 1),
        )
        assert confirmation.status_code == 201, confirmation.text
        published = client.post(
            "/api/v1/versions/52000000-0000-0000-0000-000000000001/publish",
            json={"confirmationId": confirmation.json()["data"]["confirmationId"]},
            headers=write_headers(teacher_csrf, "publish-version", 1),
        )
        assert published.status_code == 200, published.text
        assert published.json()["data"]["status"] == "published"

        client.post(
            "/api/v1/auth/logout",
            json={},
            headers={"Origin": "http://testserver", "X-CSRF-Token": teacher_csrf},
        )
        student_csrf = login(client, "student1", passwords["student1"])
        created = client.post(
            "/api/v1/tasks/51000000-0000-0000-0000-000000000001/sessions",
            json={},
            headers=write_headers(student_csrf, "student-session"),
        )
        session_id = created.json()["data"]["id"]
        sent = client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"content": "有什么依据？"},
            headers=write_headers(student_csrf, "student-message"),
        )
        assert sent.status_code == 202
        live = client.get(f"/api/v1/sessions/{session_id}/learning-report").json()["data"]
        assert live["latestReadyReport"]["metrics"]["evidenceSeekingCount"] == 1

        ended = client.post(
            f"/api/v1/sessions/{session_id}/end",
            json={},
            headers=write_headers(student_csrf, "end-session"),
        )
        assert ended.status_code == 202, ended.text
        final_report_id = ended.json()["data"]["reportId"]
        final = client.get(f"/api/v1/sessions/{session_id}/learning-report").json()["data"]
        assert final["currentReport"]["status"] == "ready"
        correction = client.post(
            f"/api/v1/sessions/{session_id}/report-corrections",
            json={"reportId": final_report_id, "text": "我仍然没有形成确定判断。"},
            headers=write_headers(student_csrf, "report-correction"),
        )
        assert correction.status_code == 201

        client.post(
            "/api/v1/auth/logout",
            json={},
            headers={"Origin": "http://testserver", "X-CSRF-Token": student_csrf},
        )
        login(client, "teacher", passwords["teacher"])
        report = client.get("/api/v1/tasks/51000000-0000-0000-0000-000000000001/report")
        assert report.status_code == 200
        data = report.json()["data"]
        assert data["kpis"] == {
            "participantCount": 1,
            "sessionCount": 1,
            "completedTurns": 1,
            "completedReportCount": 1,
        }
        assert data["students"][0]["correctionCount"] == 1
        details = client.get(
            "/api/v1/tasks/51000000-0000-0000-0000-000000000001/report/details",
            params={
                "metric": "evidenceSeekingCount",
                "aggregateToken": data["aggregateToken"],
            },
        )
        assert details.status_code == 200
        assert details.json()["data"]["items"][0]["quote"] == "有什么依据？"
