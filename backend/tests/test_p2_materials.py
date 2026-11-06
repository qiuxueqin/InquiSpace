from __future__ import annotations

import io
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlmodel import Session, select

from app import seed
from app.core.config import BACKEND_DIR, Settings
from app.db.models import AgentRun, RunEvent, Source
from app.db.session import create_db_engine
from app.main import create_app


@pytest.fixture
def app_and_passwords(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("INQUISPACE_DATA_DIR", str(tmp_path))
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    settings = Settings(
        _env_file=None,
        environment="test",
        data_dir=tmp_path,
        max_upload_bytes=1024 * 1024,
        parse_timeout_seconds=10,
    )
    passwords = {username: f"safe-{username}-password" for username, _, _ in seed.ACCOUNTS}
    engine = create_db_engine(settings)
    try:
        assert seed.seed_accounts(engine, passwords.__getitem__) == 3
    finally:
        engine.dispose()
    return create_app(settings), passwords, tmp_path


def login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["csrfToken"]


def write_headers(csrf: str, revision: int) -> dict[str, str]:
    return {
        "Origin": "http://testserver",
        "X-CSRF-Token": csrf,
        "If-Match": f'"rev-{revision}"',
    }


def create_draft(client: TestClient, csrf: str, key: str = "materials-task") -> tuple[str, str]:
    response = client.post(
        "/api/v1/tasks",
        json={"brief": {"topicName": "资料探究"}},
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf,
            "Idempotency-Key": key,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    return data["taskId"], data["draft"]["id"]


def test_txt_upload_parse_search_location_and_detach(app_and_passwords):
    app, passwords, data_dir = app_and_passwords
    with TestClient(app) as teacher:
        csrf = login(teacher, "teacher", passwords["teacher"])
        _, version_id = create_draft(teacher, csrf)
        uploaded = teacher.post(
            f"/api/v1/versions/{version_id}/sources",
            files={
                "file": (
                    "讲义.txt",
                    "第一段讨论身份变化。\n仍需核对依据。\n\n第二段说明权力变化。".encode(),
                    "text/plain",
                )
            },
            headers=write_headers(csrf, 1),
        )
        assert uploaded.status_code == 202, uploaded.text
        upload_data = uploaded.json()["data"]
        source_id = upload_data["source"]["id"]
        run_id = upload_data["run"]["id"]
        assert upload_data["revision"] == 2
        assert upload_data["source"]["status"] == "parsing"

        run = teacher.get(f"/api/v1/runs/{run_id}")
        assert run.status_code == 200
        assert run.json()["data"]["status"] == "completed"
        source = teacher.get(f"/api/v1/sources/{source_id}").json()["data"]
        assert source["status"] == "ready"
        assert source["totalLines"] == 4
        assert "storageKey" not in source

        version = teacher.get(f"/api/v1/versions/{version_id}")
        assert version.json()["data"]["revision"] == 3
        evidence_page = teacher.get(f"/api/v1/sources/{source_id}/evidence").json()["data"]
        assert len(evidence_page["items"]) == 2
        first = evidence_page["items"][0]
        assert first["startLine"] == 1
        assert first["endLine"] == 2
        located = teacher.get(f"/api/v1/evidence/{first['id']}")
        assert located.status_code == 200
        assert "第 1—2 行" in located.json()["data"]["sourceLabel"]

        text = teacher.get(f"/api/v1/sources/{source_id}/text", params={"startLine": 2, "limit": 2})
        assert text.json()["data"]["lines"] == ["仍需核对依据。", ""]
        downloaded = teacher.get(f"/api/v1/sources/{source_id}/file")
        assert downloaded.status_code == 200
        assert downloaded.content.startswith("第一段".encode())
        assert downloaded.headers["accept-ranges"] == "bytes"
        ranged = teacher.get(f"/api/v1/sources/{source_id}/file", headers={"Range": "bytes=0-5"})
        assert ranged.status_code == 206
        assert ranged.headers["content-range"].startswith("bytes 0-5/")
        assert len(ranged.content) == 6

        search = teacher.post(
            f"/api/v1/versions/{version_id}/evidence-search",
            json={"query": "权力变化", "topK": 6},
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
        )
        assert search.status_code == 200, search.text
        assert search.json()["data"]["insufficientEvidence"] is False
        assert source_id == search.json()["data"]["evidence"][0]["sourceId"]

        detached = teacher.delete(
            f"/api/v1/versions/{version_id}/sources/{source_id}",
            headers=write_headers(csrf, 3),
        )
        assert detached.status_code == 200
        assert detached.json()["data"] == {"detached": True, "revision": 4}
        assert teacher.get(f"/api/v1/sources/{source_id}").status_code == 200
        path_count = len(list((data_dir / "uploads").glob(f"**/{source_id}.txt")))
        assert path_count == 1


def test_upload_rejects_bad_type_bytes_and_stale_revision(app_and_passwords):
    app, passwords, _ = app_and_passwords
    with TestClient(app) as teacher:
        csrf = login(teacher, "teacher", passwords["teacher"])
        _, version_id = create_draft(teacher, csrf, "bad-files")
        bad = teacher.post(
            f"/api/v1/versions/{version_id}/sources",
            files={"file": ("fake.pdf", b"plain text", "application/pdf")},
            headers=write_headers(csrf, 1),
        )
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
        unsupported = teacher.post(
            f"/api/v1/versions/{version_id}/sources",
            files={"file": ("notes.docx", b"document", "application/octet-stream")},
            headers=write_headers(csrf, 1),
        )
        assert unsupported.status_code == 422
        assert unsupported.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
        stale = teacher.post(
            f"/api/v1/versions/{version_id}/sources",
            files={"file": ("ok.txt", "内容".encode(), "text/plain")},
            headers=write_headers(csrf, 2),
        )
        assert stale.status_code == 412
        assert stale.json()["error"]["code"] == "REVISION_CONFLICT"


def test_failed_txt_and_scanned_pdf_are_atomic(app_and_passwords):
    app, passwords, _ = app_and_passwords
    with TestClient(app) as teacher:
        csrf = login(teacher, "teacher", passwords["teacher"])
        _, version_id = create_draft(teacher, csrf, "failed-parsing")
        invalid = teacher.post(
            f"/api/v1/versions/{version_id}/sources",
            files={"file": ("bad.txt", b"\xff\xfe", "text/plain")},
            headers=write_headers(csrf, 1),
        )
        invalid_source = invalid.json()["data"]["source"]["id"]
        failed = teacher.get(f"/api/v1/sources/{invalid_source}").json()["data"]
        assert failed["status"] == "failed"
        assert failed["parseError"]["code"] == "TEXT_DECODE_FAILED"
        assert (
            teacher.get(f"/api/v1/sources/{invalid_source}/evidence").json()["data"]["items"] == []
        )

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        stream = io.BytesIO()
        writer.write(stream)
        scanned = teacher.post(
            f"/api/v1/versions/{version_id}/sources",
            files={"file": ("scan.pdf", stream.getvalue(), "application/pdf")},
            headers=write_headers(csrf, 2),
        )
        scan_source = scanned.json()["data"]["source"]["id"]
        scan_state = teacher.get(f"/api/v1/sources/{scan_source}").json()["data"]
        assert scan_state["status"] == "failed"
        assert scan_state["parseError"]["code"] == "OCR_REQUIRED"


def test_owner_scope_and_ready_source_reuse(app_and_passwords):
    app, passwords, _ = app_and_passwords
    with TestClient(app) as teacher, TestClient(app) as student:
        csrf = login(teacher, "teacher", passwords["teacher"])
        _, first_version = create_draft(teacher, csrf, "reuse-1")
        upload = teacher.post(
            f"/api/v1/versions/{first_version}/sources",
            files={"file": ("reuse.txt", "可复用资料".encode(), "text/plain")},
            headers=write_headers(csrf, 1),
        )
        source_id = upload.json()["data"]["source"]["id"]
        student_csrf = login(student, "student1", passwords["student1"])
        assert student.get(f"/api/v1/sources/{source_id}").status_code == 404
        assert (
            student.post(
                f"/api/v1/versions/{first_version}/evidence-search",
                json={"query": "资料"},
                headers={"Origin": "http://testserver", "X-CSRF-Token": student_csrf},
            ).status_code
            == 403
        )
        assert teacher.get(f"/api/v1/versions/{first_version}/sources").status_code == 200


def test_startup_marks_interrupted_parse_failed(app_and_passwords):
    app, passwords, _ = app_and_passwords
    with TestClient(app) as teacher:
        csrf = login(teacher, "teacher", passwords["teacher"])
        _, version_id = create_draft(teacher, csrf, "startup-recovery")
        uploaded = teacher.post(
            f"/api/v1/versions/{version_id}/sources",
            files={"file": ("recovery.txt", "恢复测试".encode(), "text/plain")},
            headers=write_headers(csrf, 1),
        )
        run_id = uploaded.json()["data"]["run"]["id"]
        source_id = uploaded.json()["data"]["source"]["id"]
        with Session(app.state.engine) as session:
            run = session.get(AgentRun, run_id)
            source = session.get(Source, source_id)
            assert run is not None and source is not None
            run.status = "running"
            run.finished_at = None
            run.result_json = None
            run.error_json = None
            source.status = "parsing"
            source.parser_version = None
            source.page_count = None
            source.total_lines = None
            session.commit()
    with TestClient(app):
        with Session(app.state.engine) as session:
            recovered = session.get(AgentRun, run_id)
            recovered_source = session.get(Source, source_id)
            assert recovered is not None and recovered_source is not None
            assert recovered.status == "failed"
            assert recovered.terminal_reason == "PROCESS_INTERRUPTED"
            assert recovered_source.status == "failed"
            events = session.exec(
                select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
            ).all()
            assert events[-1].event_type == "run.failed"
