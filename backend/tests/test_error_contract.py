from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app
from app.schemas.common import ErrorDetail


def test_error_details_are_independent_objects():
    first = ErrorDetail(code="FIRST", message="第一项")
    second = ErrorDetail(code="SECOND", message="第二项")
    first.details["currentRevision"] = 4
    assert second.details == {}


def test_business_error_matches_document_and_request_id(tmp_path: Path):
    app = create_app(Settings(_env_file=None, environment="test", data_dir=tmp_path))

    @app.get("/test/conflict")
    def conflict():
        raise AppError(
            "REVISION_CONFLICT",
            "内容已变化，请重新载入",
            status_code=412,
            details={"currentRevision": 4},
        )

    with TestClient(app) as client:
        response = client.get("/test/conflict", headers={"X-Request-ID": "client-supplied"})
        assert response.status_code == 412
        body = response.json()
        assert body["error"] == {
            "code": "REVISION_CONFLICT",
            "message": "内容已变化，请重新载入",
            "details": {"currentRevision": 4},
            "retryable": False,
        }
        assert body["requestId"] == response.headers["X-Request-ID"]
        assert body["requestId"] != "client-supplied"
        assert client.get("/api/absent").json()["error"]["details"] == {}
