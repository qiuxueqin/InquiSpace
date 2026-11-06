"""P5 publication, learning process, and teacher-report routes."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Header, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse

from app.api.dependencies import (
    CSRFProtected,
    CurrentUser,
    DatabaseSession,
    TeacherCSRF,
    TeacherUser,
)
from app.core.errors import AppError
from app.integrations.deepseek_model import create_model
from app.schemas.p5_dtos import (
    ArchiveRequest,
    DeletedResult,
    EvaluationRequest,
    ExportRequest,
    LearningEventRequest,
    NoteCreateRequest,
    NotePatchRequest,
    PublishRequest,
    ReportCorrectionRequest,
    RestoreRequest,
)
from app.schemas.session_dtos import EmptyRequest
from app.services import idempotency, learning, publication, tasks, teacher_reports

router = APIRouter(tags=["Publication and reports"])


def _envelope(
    request: Request, data: object, status: int = 200, etag: str | None = None
) -> JSONResponse:
    headers = {"X-Request-ID": request.state.request_id}
    if etag is not None:
        headers["ETag"] = etag
    return JSONResponse(
        status_code=status,
        content={"data": jsonable_encoder(data), "requestId": request.state.request_id},
        headers=headers,
    )


def _reserve(
    request: Request,
    session: DatabaseSession,
    user_id: str,
    key: str | None,
    body: object,
    extra: str = "",
):
    reservation = idempotency.begin(
        session,
        user_id=user_id,
        method="POST",
        path=request.url.path,
        key=key,
        digest=idempotency.request_hash(
            "POST", request.url.path, jsonable_encoder(body), extra=extra
        ),
    )
    return reservation


def _complete(
    session: DatabaseSession, reservation, data: object, status: int, resource_id: str | None = None
) -> None:
    idempotency.complete(
        session,
        reservation,
        status=status,
        body=jsonable_encoder(data),
        resource_id=resource_id,
    )
    session.commit()


def _schedule_report(
    request: Request,
    background: BackgroundTasks,
    report_id: str | None,
    *,
    schedule_all: bool = False,
) -> None:
    if report_id is None and not schedule_all:
        return
    settings = request.app.state.settings
    background.add_task(
        learning.resume_pending_reports,
        request.app.state.engine,
        settings,
        request.app.state.workflow_runtime,
        create_model,
    )


@router.post("/versions/{version_id}/publish")
def publish(
    request: Request,
    version_id: str,
    payload: PublishRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    expected = tasks.parse_if_match(if_match)
    reservation = _reserve(request, session, user.id, idempotency_key, payload, f"rev-{expected}")
    if reservation.replay is not None:
        return _envelope(request, reservation.replay.body, reservation.replay.status)
    data, cancelled_run_ids = publication.publish_version(
        session, user, version_id, payload.confirmation_id, expected_revision=expected
    )
    _complete(session, reservation, data, 200, version_id)
    for run_id in cancelled_run_ids:
        request.app.state.workflow_runtime.cancel(run_id)
    return _envelope(request, data)


@router.post("/tasks/{task_id}/archive")
def archive(
    request: Request,
    task_id: str,
    payload: ArchiveRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    reservation = _reserve(request, session, user.id, idempotency_key, payload)
    if reservation.replay is not None:
        return _envelope(request, reservation.replay.body, reservation.replay.status)
    data, run_ids = publication.archive_task(
        session, user, task_id, payload.confirmation_id, payload.expected_task_revision
    )
    _complete(session, reservation, data, 200, task_id)
    for run_id in run_ids:
        request.app.state.workflow_runtime.cancel(run_id)
    return _envelope(request, data)


@router.post("/tasks/{task_id}/restore")
def restore(
    request: Request,
    task_id: str,
    payload: RestoreRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    reservation = _reserve(request, session, user.id, idempotency_key, payload)
    if reservation.replay is not None:
        return _envelope(request, reservation.replay.body, reservation.replay.status)
    data = publication.restore_task(session, user, task_id, payload.expected_task_revision)
    _complete(session, reservation, data, 200, task_id)
    return _envelope(request, data)


@router.post("/sessions/{session_id}/end")
def end_session(
    request: Request,
    background: BackgroundTasks,
    session_id: str,
    _payload: EmptyRequest,
    session: DatabaseSession,
    auth: CSRFProtected,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    user = auth[1]
    reservation = _reserve(request, session, user.id, idempotency_key, {})
    if reservation.replay is not None:
        return _envelope(request, reservation.replay.body, reservation.replay.status)
    data = learning.end_session(session, user, session_id)
    status = 202 if data.report_id else 200
    _complete(session, reservation, data, status, data.report_id or session_id)
    _schedule_report(request, background, data.report_id)
    return _envelope(request, data, status)


@router.get("/sessions/{session_id}/notes")
def list_notes(
    request: Request,
    session_id: str,
    session: DatabaseSession,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
) -> JSONResponse:
    return _envelope(
        request, learning.list_notes(session, user, session_id, limit=limit, cursor=cursor)
    )


@router.post("/sessions/{session_id}/notes", status_code=201)
def create_note(
    request: Request,
    background: BackgroundTasks,
    session_id: str,
    payload: NoteCreateRequest,
    session: DatabaseSession,
    auth: CSRFProtected,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    user = auth[1]
    reservation = _reserve(request, session, user.id, idempotency_key, payload)
    if reservation.replay is not None:
        return _envelope(request, reservation.replay.body, reservation.replay.status)
    data = learning.create_note(session, user, session_id, payload)
    _complete(session, reservation, data, 201, data.id)
    _schedule_report(request, background, None, schedule_all=True)
    return _envelope(request, data, 201, tasks._etag(data.row_version))


@router.patch("/notes/{note_id}")
def update_note(
    request: Request,
    background: BackgroundTasks,
    note_id: str,
    payload: NotePatchRequest,
    session: DatabaseSession,
    auth: CSRFProtected,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> JSONResponse:
    data = learning.update_note(session, auth[1], note_id, payload, tasks.parse_if_match(if_match))
    session.commit()
    _schedule_report(request, background, None, schedule_all=True)
    return _envelope(request, data, etag=tasks._etag(data.row_version))


@router.delete("/notes/{note_id}")
def delete_note(
    request: Request,
    background: BackgroundTasks,
    note_id: str,
    session: DatabaseSession,
    auth: CSRFProtected,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> JSONResponse:
    learning.delete_note(session, auth[1], note_id, tasks.parse_if_match(if_match))
    session.commit()
    _schedule_report(request, background, None, schedule_all=True)
    return _envelope(request, DeletedResult(deleted=True))


@router.get("/sessions/{session_id}/submission")
def get_submission(
    request: Request, session_id: str, session: DatabaseSession, user: CurrentUser
) -> JSONResponse:
    return _envelope(request, learning.legacy_submission(session, user, session_id))


@router.put("/sessions/{session_id}/submission")
@router.post("/sessions/{session_id}/submission/submit")
def legacy_write_disabled(request: Request, session_id: str, auth: CSRFProtected) -> JSONResponse:
    del request, session_id, auth
    raise AppError("LEGACY_WRITE_DISABLED", "旧成果表写入已停用，请直接结束探究", 410)


@router.post("/sessions/{session_id}/learning-events")
def learning_event(
    request: Request,
    background: BackgroundTasks,
    session_id: str,
    payload: LearningEventRequest,
    session: DatabaseSession,
    auth: CSRFProtected,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    user = auth[1]
    reservation = _reserve(request, session, user.id, idempotency_key, payload)
    if reservation.replay is not None:
        return _envelope(request, reservation.replay.body, reservation.replay.status)
    data, status, changed = learning.record_event(session, user, session_id, payload)
    _complete(session, reservation, data, status, data.id)
    if changed:
        _schedule_report(request, background, None, schedule_all=True)
    return _envelope(request, data, status, tasks._etag(data.row_version))


@router.get("/sessions/{session_id}/learning-report")
def get_learning_report(
    request: Request, session_id: str, session: DatabaseSession, user: CurrentUser
) -> JSONResponse:
    return _envelope(request, learning.report_envelope(session, user, session_id))


@router.post("/sessions/{session_id}/report-corrections", status_code=201)
def add_correction(
    request: Request,
    session_id: str,
    payload: ReportCorrectionRequest,
    session: DatabaseSession,
    auth: CSRFProtected,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    user = auth[1]
    reservation = _reserve(request, session, user.id, idempotency_key, payload)
    if reservation.replay is not None:
        return _envelope(request, reservation.replay.body, reservation.replay.status)
    data = learning.add_correction(session, user, session_id, payload.report_id, payload.text)
    _complete(session, reservation, data, 201, data.id)
    return _envelope(request, data, 201)


@router.get("/sessions/{session_id}/report-corrections")
def list_corrections(
    request: Request,
    session_id: str,
    session: DatabaseSession,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
) -> JSONResponse:
    return _envelope(
        request, learning.list_corrections(session, user, session_id, limit=limit, cursor=cursor)
    )


@router.post("/learning-reports/{report_id}/retry")
def retry_report(
    request: Request,
    background: BackgroundTasks,
    report_id: str,
    _payload: EmptyRequest,
    session: DatabaseSession,
    auth: CSRFProtected,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    user = auth[1]
    reservation = _reserve(request, session, user.id, idempotency_key, {})
    if reservation.replay is not None:
        return _envelope(request, reservation.replay.body, reservation.replay.status)
    data, status, queued = learning.retry_report(session, user, report_id)
    _complete(session, reservation, data, status, report_id)
    _schedule_report(request, background, queued)
    return _envelope(request, data, status)


@router.post("/sessions/{session_id}/learning-reports")
def ensure_report(
    request: Request,
    background: BackgroundTasks,
    session_id: str,
    _payload: EmptyRequest,
    session: DatabaseSession,
    auth: CSRFProtected,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    user = auth[1]
    reservation = _reserve(request, session, user.id, idempotency_key, {})
    if reservation.replay is not None:
        return _envelope(request, reservation.replay.body, reservation.replay.status)
    data, status, queued = learning.ensure_report(session, user, session_id)
    _complete(session, reservation, data, status, data.report_id)
    _schedule_report(request, background, queued)
    return _envelope(request, data, status)


@router.get("/tasks/{task_id}/report")
def get_teacher_report(
    request: Request,
    task_id: str,
    session: DatabaseSession,
    user: TeacherUser,
    scope: Literal["latest", "all", "version"] = "latest",
    version_id: str | None = Query(default=None, alias="versionId"),
    state: Literal["all", "active", "ended"] = "all",
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
) -> JSONResponse:
    return _envelope(
        request,
        teacher_reports.teacher_report(
            session,
            user,
            task_id,
            scope=scope,
            version_id=version_id,
            state=state,
            limit=limit,
            cursor=cursor,
        ),
    )


@router.get("/tasks/{task_id}/report/details")
def get_report_details(
    request: Request,
    task_id: str,
    session: DatabaseSession,
    user: TeacherUser,
    metric: str,
    aggregate_token: str = Query(alias="aggregateToken"),
    scope: Literal["latest", "all", "version"] = "latest",
    version_id: str | None = Query(default=None, alias="versionId"),
    session_id: str | None = Query(default=None, alias="sessionId"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
) -> JSONResponse:
    return _envelope(
        request,
        teacher_reports.report_details(
            session,
            user,
            task_id,
            scope=scope,
            version_id=version_id,
            metric=metric,
            aggregate_token=aggregate_token,
            session_id=session_id,
            limit=limit,
            cursor=cursor,
        ),
    )


@router.get("/sessions/{session_id}/reviews")
def list_reviews(
    request: Request,
    session_id: str,
    session: DatabaseSession,
    user: TeacherUser,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
) -> JSONResponse:
    return _envelope(
        request, teacher_reports.list_reviews(session, user, session_id, limit=limit, cursor=cursor)
    )


@router.post("/sessions/{session_id}/evaluations", status_code=201)
def add_evaluation(
    request: Request,
    session_id: str,
    payload: EvaluationRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    reservation = _reserve(request, session, user.id, idempotency_key, payload)
    if reservation.replay is not None:
        return _envelope(request, reservation.replay.body, reservation.replay.status)
    review_id = teacher_reports.add_evaluation(session, user, session_id, payload)
    data = {"reviewId": review_id}
    _complete(session, reservation, data, 201, review_id)
    return _envelope(request, data, 201)


@router.post("/tasks/{task_id}/report-exports")
def export_report(
    request: Request,
    task_id: str,
    payload: ExportRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
) -> HTMLResponse:
    rendered = teacher_reports.render_export(
        session,
        user,
        task_id,
        scope=payload.scope,
        version_id=payload.version_id,
        aggregate_token=payload.aggregate_token,
    )
    return HTMLResponse(
        rendered,
        headers={
            "Content-Disposition": (
                "attachment; filename*=UTF-8''"
                "%E7%9F%A5%E5%A2%83_%E6%95%99%E5%AD%A6%E6%8A%A5%E5%91%8A.html"
            ),
            "Cache-Control": "no-store",
        },
    )
