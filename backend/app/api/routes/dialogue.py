"""D06 and F01--F05/F07 role-session APIs."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.dependencies import (
    CSRFProtected,
    CurrentUser,
    DatabaseSession,
    SettingsDependency,
    TeacherCSRF,
)
from app.integrations.deepseek_model import create_model
from app.schemas.session_dtos import EmptyRequest, SendMessageRequest
from app.services import dialogue, idempotency, learning, tasks

router = APIRouter(tags=["Dialogue"])


def _envelope(request: Request, data: object, status: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"data": jsonable_encoder(data), "requestId": request.state.request_id},
    )


@router.post("/versions/{version_id}/preview-sessions", status_code=201)
def create_preview_session(
    request: Request,
    version_id: str,
    _payload: EmptyRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    expected = tasks.parse_if_match(if_match)
    path = request.url.path
    reservation = idempotency.begin(
        session,
        user_id=user.id,
        method="POST",
        path=path,
        key=idempotency_key,
        digest=idempotency.request_hash("POST", path, {}, extra=f"rev-{expected}"),
    )
    if reservation.replay is not None:
        return _envelope(request, reservation.replay.body, reservation.replay.status)
    data = dialogue.create_preview_session(session, user, version_id, expected)
    idempotency.complete(
        session, reservation, status=201, body=data.model_dump(by_alias=True), resource_id=data.id
    )
    session.commit()
    return _envelope(request, data, 201)


@router.post("/tasks/{task_id}/sessions")
def create_student_session(
    request: Request,
    task_id: str,
    _payload: EmptyRequest,
    session: DatabaseSession,
    auth: CSRFProtected,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    user = auth[1]
    path = request.url.path
    reservation = idempotency.begin(
        session,
        user_id=user.id,
        method="POST",
        path=path,
        key=idempotency_key,
        digest=idempotency.request_hash("POST", path, {}),
    )
    if reservation.replay is not None:
        return _envelope(request, reservation.replay.body, reservation.replay.status)
    data, status = dialogue.create_student_session(session, user, task_id)
    idempotency.complete(
        session,
        reservation,
        status=status,
        body=data.model_dump(by_alias=True),
        resource_id=data.id,
    )
    session.commit()
    return _envelope(request, data, status)


@router.get("/sessions/{session_id}")
def get_session(
    request: Request, session_id: str, session: DatabaseSession, user: CurrentUser
) -> JSONResponse:
    return _envelope(request, dialogue.get_session(session, user, session_id))


@router.get("/sessions/{session_id}/messages")
def list_messages(
    request: Request,
    session_id: str,
    session: DatabaseSession,
    user: CurrentUser,
    after_seq: int = Query(default=0, ge=0, alias="afterSeq"),
    limit: int = Query(default=50, ge=1, le=100),
) -> JSONResponse:
    return _envelope(
        request, dialogue.list_messages(session, user, session_id, after_seq=after_seq, limit=limit)
    )


@router.post("/sessions/{session_id}/messages", status_code=202)
def send_message(
    request: Request,
    background: BackgroundTasks,
    session_id: str,
    payload: SendMessageRequest,
    session: DatabaseSession,
    auth: CSRFProtected,
    settings: SettingsDependency,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    data, status, run_id = dialogue.start_message(
        session,
        auth[1],
        session_id,
        payload.content,
        settings,
        path=request.url.path,
        idempotency_key=idempotency_key,
    )
    if status == 202:
        background.add_task(
            dialogue.process_chat,
            request.app.state.engine,
            settings,
            create_model(settings),
            request.app.state.workflow_runtime,
            run_id,
        )
        background.add_task(
            learning.resume_pending_reports,
            request.app.state.engine,
            settings,
            request.app.state.workflow_runtime,
            create_model,
        )
    return _envelope(request, data, status)


@router.post("/sessions/{session_id}/summaries", status_code=202)
def start_summary(
    request: Request,
    background: BackgroundTasks,
    session_id: str,
    _payload: EmptyRequest,
    session: DatabaseSession,
    auth: CSRFProtected,
    settings: SettingsDependency,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    data, status, run_id = dialogue.start_summary(
        session,
        auth[1],
        session_id,
        settings,
        path=request.url.path,
        idempotency_key=idempotency_key,
    )
    if status == 202:
        background.add_task(
            dialogue.process_summary,
            request.app.state.engine,
            settings,
            create_model(settings),
            request.app.state.workflow_runtime,
            run_id,
        )
    return _envelope(request, data, status)


@router.get("/tasks/{task_id}/sessions")
def list_task_sessions(
    request: Request,
    task_id: str,
    session: DatabaseSession,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> JSONResponse:
    return _envelope(
        request, dialogue.list_task_sessions(session, user, task_id, limit=limit, cursor=cursor)
    )
