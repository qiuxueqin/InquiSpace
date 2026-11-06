from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import BACKEND_DIR, Settings
from app.main import create_app
from app.schemas.common import APIModel


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, environment="test", data_dir=tmp_path / "data")


def test_health_and_storage(settings: Settings):
    app = create_app(settings)
    assert not settings.data_dir.exists()
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["database"] == "ok"
        assert body["requestId"] == response.headers["X-Request-ID"]
        assert (settings.data_dir / "uploads").is_dir()
        with app.state.engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
            assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 5000
            assert connection.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"
            assert connection.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
        assert client.get("/api/v1/health").json()["requestId"] != body["requestId"]


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("GET", "/api/v1/tasks", 401),
        ("POST", "/api/v1/health", 405),
    ],
)
def test_http_errors(settings: Settings, method: str, path: str, status: int):
    with TestClient(create_app(settings)) as client:
        response = client.request(method, path)
        assert response.status_code == status
        expected_code = "AUTHENTICATION_REQUIRED" if status == 401 else f"HTTP_{status}"
        assert response.json()["error"]["code"] == expected_code
        assert response.json()["requestId"] == response.headers["X-Request-ID"]


def test_validation_and_internal_errors_do_not_echo_input(settings: Settings):
    app = create_app(settings)

    class Payload(APIModel):
        max_steps: int

    @app.post("/test/validate")
    def validate(payload: Payload):
        return payload

    @app.get("/test/failure")
    def fail():
        raise RuntimeError("sensitive-internal-detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/test/validate", json={"maxSteps": "secret-input"})
        assert response.status_code == 422
        assert "secret-input" not in response.text
        assert response.json()["error"]["details"]["fields"][0]["field"] == "body.maxSteps"
        response = client.get("/test/failure")
        assert response.status_code == 500
        assert "sensitive-internal-detail" not in response.text
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert response.headers["X-Request-ID"] == response.json()["requestId"]


def test_openapi_uses_camel_case(settings: Settings):
    with TestClient(create_app(settings)) as client:
        schema = client.get("/api/openapi.json").json()
        envelope = schema["components"]["schemas"]["Envelope_Health_"]
        assert "requestId" in envelope["properties"]
        assert "/api/v1/health" in schema["paths"]
        components = schema["components"]["schemas"]
        assert "TaskBrief" in components
        assert "RoleCardInput" in components
        assert "ReportContent" in components
        assert "stepCount" not in str(components["RunView_ReportRunResult_"])


def test_production_disables_docs(settings: Settings):
    settings.environment = "production"
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/docs").status_code == 404
        assert client.get("/api/openapi.json").status_code == 404


def test_frontend_hosting(settings: Settings, tmp_path: Path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>InquiSpace</html>")
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text("export {}")
    settings.serve_frontend = True
    settings.frontend_dist = dist
    with TestClient(create_app(settings)) as client:
        assert "InquiSpace" in client.get("/teacher/tasks").text
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/assets/missing.js").status_code == 404
        assert client.get("/api/unknown").status_code == 404
        assert client.get("/api/v1/health").json()["data"]["status"] == "ok"
        assert client.get("/%2e%2e/outside.txt").status_code == 404


def test_missing_frontend_build_fails_clearly(settings: Settings, tmp_path: Path):
    settings.serve_frontend = True
    settings.frontend_dist = tmp_path / "missing"
    with pytest.raises(RuntimeError, match="Frontend build missing"):
        create_app(settings)


def test_migration_baseline_is_repeatable(settings: Settings, monkeypatch):
    monkeypatch.setenv("INQUISPACE_DATA_DIR", str(settings.data_dir))
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health").status_code == 200
        with client.app.state.engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == ScriptDirectory.from_config(config).get_current_head()
            )
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    command.downgrade(config, "base")
    command.upgrade(config, "head")
