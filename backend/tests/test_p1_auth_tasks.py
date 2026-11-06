from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app import seed
from app.core.config import BACKEND_DIR, Settings
from app.db.session import create_db_engine
from app.main import create_app


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
    return create_app(settings), passwords


def login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["csrfToken"]


def test_login_me_logout_and_security(app_and_passwords):
    app, passwords = app_and_passwords
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v1/auth/login", json={"username": "teacher", "password": passwords["teacher"]}
            ).status_code
            == 403
        )
        csrf = login(client, "teacher", passwords["teacher"])
        me = client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["data"]["user"] == {
            "id": me.json()["data"]["user"]["id"],
            "displayName": "教师",
            "role": "teacher",
        }
        assert me.json()["data"]["csrfToken"] == csrf
        assert (
            client.post(
                "/api/v1/auth/logout", json={}, headers={"Origin": "http://testserver"}
            ).status_code
            == 403
        )
        logout = client.post(
            "/api/v1/auth/logout",
            json={},
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
        )
        assert logout.status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 401


def test_teacher_task_create_requires_csrf_and_idempotency(app_and_passwords):
    app, passwords = app_and_passwords
    with TestClient(app) as client:
        csrf = login(client, "teacher", passwords["teacher"])
        headers = {"Origin": "http://testserver", "X-CSRF-Token": csrf}
        assert (
            client.post(
                "/api/v1/tasks", json={}, headers={"Origin": "http://testserver"}
            ).status_code
            == 403
        )
        missing_key = client.post("/api/v1/tasks", json={}, headers=headers)
        assert missing_key.status_code == 428
        headers["Idempotency-Key"] = "create-1"
        created = client.post(
            "/api/v1/tasks", json={"teachingIntent": "探究历史背景"}, headers=headers
        )
        assert created.status_code == 201, created.text
        body = created.json()["data"]
        assert body["taskRevision"] == 1
        assert body["draft"]["brief"]["subject"] == "历史"
        replay = client.post(
            "/api/v1/tasks", json={"teachingIntent": "探究历史背景"}, headers=headers
        )
        assert replay.status_code == 201
        assert replay.json()["data"]["taskId"] == body["taskId"]
        conflict = client.post("/api/v1/tasks", json={"teachingIntent": "其他"}, headers=headers)
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_revision_etag_and_cross_user_visibility(app_and_passwords):
    app, passwords = app_and_passwords
    with TestClient(app) as teacher, TestClient(app) as student:
        csrf = login(teacher, "teacher", passwords["teacher"])
        created = teacher.post(
            "/api/v1/tasks",
            json={"brief": {"topicName": "清朝灭亡"}},
            headers={
                "Origin": "http://testserver",
                "X-CSRF-Token": csrf,
                "Idempotency-Key": "create-2",
            },
        )
        task_id = created.json()["data"]["taskId"]
        version_id = created.json()["data"]["draft"]["id"]
        assert teacher.get(f"/api/v1/versions/{version_id}").headers["ETag"] == '"rev-1"'
        patch_headers = {"Origin": "http://testserver", "X-CSRF-Token": csrf, "If-Match": '"rev-1"'}
        updated = teacher.patch(
            f"/api/v1/versions/{version_id}",
            json={"brief": {"background": "背景"}},
            headers=patch_headers,
        )
        assert updated.status_code == 200
        assert updated.headers["ETag"] == '"rev-2"'
        assert (
            teacher.patch(
                f"/api/v1/versions/{version_id}",
                json={"teachingIntent": "弱格式"},
                headers={"Origin": "http://testserver", "X-CSRF-Token": csrf, "If-Match": "rev-2"},
            ).status_code
            == 428
        )
        stale = teacher.patch(
            f"/api/v1/versions/{version_id}",
            json={"teachingIntent": "过期"},
            headers=patch_headers,
        )
        assert stale.status_code == 412
        assert stale.json()["error"]["code"] == "REVISION_CONFLICT"
        student_csrf = login(student, "student1", passwords["student1"])
        assert student.get(f"/api/v1/tasks/{task_id}").status_code == 404
        roster = student.get("/api/v1/users", params={"role": "student"})
        assert roster.status_code == 403
        assert (
            student.post(
                "/api/v1/tasks",
                json={},
                headers={
                    "Origin": "http://testserver",
                    "X-CSRF-Token": student_csrf,
                    "Idempotency-Key": "student",
                },
            ).status_code
            == 403
        )
