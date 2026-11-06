"""G01--G05 shared Run APIs and persisted SSE replay."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from sqlmodel import Session

from app.api.dependencies import CSRFProtected, CurrentUser, DatabaseSession, SettingsDependency
from app.core.errors import AppError
from app.db.models import User
from app.integrations.deepseek_model import create_model
from app.schemas.session_dtos import CancelRunRequest, EmptyRequest
from app.services import dialogue, runs

router = APIRouter(prefix="/runs", tags=["Runs"])


def _envelope(request: Request, data: object, status: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"data": jsonable_encoder(data), "requestId": request.state.request_id},
    )


@router.get("/{run_id}")
def get_run(
    request: Request, run_id: str, session: DatabaseSession, user: CurrentUser
) -> JSONResponse:
    return _envelope(request, runs.get_run(session, user, run_id))


@router.get("/{run_id}/events")
def stream_events(
    request: Request,
    run_id: str,
    session: DatabaseSession,
    user: CurrentUser,
    after_seq: int = Query(default=0, ge=0, alias="afterSeq"),
) -> StreamingResponse:
    runs.authorize(session, user, run_id)
    user_id = user.id

    async def event_stream():
        cursor = after_seq
        idle = 0
        while True:
            if await request.is_disconnected():
                return
            with Session(request.app.state.engine) as db:
                current_user = db.get(User, user_id)
                if current_user is None:
                    return
                try:
                    events, terminal = runs.list_events(db, current_user, run_id, cursor)
                except AppError:
                    return
            if events:
                idle = 0
                for seq, event_type, payload in events:
                    cursor = seq
                    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                    yield f"id: {seq}\nevent: {event_type}\ndata: {data}\n\n"
                if terminal:
                    return
            elif terminal:
                return
            else:
                idle += 1
                if idle >= 30:
                    with Session(request.app.state.engine) as db:
                        current_user = db.get(User, user_id)
                        if current_user is None:
                            return
                        try:
                            runs.authorize(db, current_user, run_id)
                        except AppError:
                            return
                    yield ": heartbeat\n\n"
                    idle = 0
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{run_id}/cancel")
def cancel_run(
    request: Request,
    run_id: str,
    payload: CancelRunRequest,
    session: DatabaseSession,
    auth: CSRFProtected,
) -> JSONResponse:
    row = runs.cancel(session, auth[1], run_id, payload.reason, request.app.state.workflow_runtime)
    status = 202 if row.cancel_requested_at is not None and row.status == "cancelled" else 200
    return _envelope(
        request,
        {
            "runId": row.id,
            "cancelRequested": row.cancel_requested_at is not None,
            "status": row.status,
        },
        status,
    )


@router.post("/{run_id}/retry", status_code=202)
def retry_run(
    request: Request,
    background: BackgroundTasks,
    run_id: str,
    _payload: EmptyRequest,
    session: DatabaseSession,
    auth: CSRFProtected,
    settings: SettingsDependency,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    data, status, new_run_id = runs.retry(
        session,
        auth[1],
        run_id,
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
            new_run_id,
        )
    return _envelope(request, data, status)


@router.get("/{run_id}/steps")
def internal_steps(_run_id: str, user: CurrentUser) -> None:
    raise AppError("INTERNAL_DIAGNOSTIC_ONLY", "运行诊断记录不向师生界面开放", 410)
