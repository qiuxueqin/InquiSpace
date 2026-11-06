"""D01--D05, D07--D09 and P3-scoped E01/G03 backend routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.dependencies import (
    CSRFProtected,
    DatabaseSession,
    SettingsDependency,
    TeacherCSRF,
    TeacherUser,
)
from app.integrations.deepseek_model import create_model
from app.schemas.p3_dtos import (
    ApplyRoleCandidateRequest,
    CancelRunRequest,
    CreateConfirmationRequest,
    EmptyRequest,
    PlanGenerationRequest,
    RoleGenerationRequest,
    SaveRoleCardRequest,
)
from app.services import idempotency, materials, p3, tasks
from app.workflows.runtime import WorkflowRuntime

router = APIRouter(prefix="/versions", tags=["Plan and roles"])
runs_router = APIRouter(prefix="/runs", tags=["Runs"])


def _envelope(
    request: Request, data: object, *, status: int = 200, etag: str | None = None
) -> JSONResponse:
    headers = {"X-Request-ID": request.state.request_id}
    if etag is not None:
        headers["ETag"] = etag
    return JSONResponse(
        status_code=status,
        content={"data": jsonable_encoder(data), "requestId": request.state.request_id},
        headers=headers,
    )


def _run_with_capacity(
    runtime: WorkflowRuntime,
    worker,
    engine,
    settings,
    model,
    run_id: str,
) -> None:
    if not runtime.acquire_model_slot():
        from sqlmodel import Session

        from app.db.models import AgentRun
        from app.integrations.model import ModelAdapterError

        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            if run is not None and run.status == "running":
                p3._fail_run(
                    session,
                    run,
                    ModelAdapterError(
                        "MODEL_CAPACITY_EXCEEDED", "模型服务繁忙，请稍后重试", retryable=True
                    ),
                )
        return
    try:
        worker(engine, settings, model, run_id)
    finally:
        runtime.release_model_slot()


def _start_background(
    request: Request,
    background: BackgroundTasks,
    worker,
    run_id: str,
) -> None:
    settings = request.app.state.settings
    background.add_task(
        _run_with_capacity,
        request.app.state.workflow_runtime,
        worker,
        request.app.state.engine,
        settings,
        create_model(settings),
        run_id,
    )


def _reserve_idempotency(
    request: Request,
    session: DatabaseSession,
    user_id: str,
    key: str | None,
    body: object,
    expected_revision: int,
):
    reservation = idempotency.begin(
        session,
        user_id=user_id,
        method="POST",
        path=request.url.path,
        key=key,
        digest=idempotency.request_hash(
            "POST", request.url.path, jsonable_encoder(body), extra=f"rev-{expected_revision}"
        ),
    )
    if reservation.replay is not None:
        return reservation, _envelope(
            request, reservation.replay.body, status=reservation.replay.status
        )
    return reservation, None


def _complete_idempotency(
    session: DatabaseSession,
    reservation,
    data: object,
    status: int,
    resource_id: str | None,
) -> None:
    idempotency.complete(
        session,
        reservation,
        status=status,
        body=jsonable_encoder(data),
        resource_id=resource_id,
    )
    session.commit()


@router.post("/{version_id}/role-generations", status_code=202)
def start_role_generation(
    request: Request,
    background: BackgroundTasks,
    version_id: str,
    payload: RoleGenerationRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
    settings: SettingsDependency,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    expected = tasks.parse_if_match(if_match)
    reservation, replay = _reserve_idempotency(
        request, session, user.id, idempotency_key, payload, expected
    )
    if replay is not None:
        return replay
    run = p3.start_role_generation(
        session,
        user,
        version_id,
        expected_revision=expected,
        instruction=payload.instruction,
        settings=settings,
    )
    data = materials.run_view(run)
    _complete_idempotency(session, reservation, data, 202, run.id)
    _start_background(request, background, p3.process_role_generation, run.id)
    return _envelope(request, data, status=202)


@router.get("/{version_id}/role-card")
def get_role_card(
    request: Request, version_id: str, session: DatabaseSession, user: TeacherUser
) -> JSONResponse:
    data = p3.get_role_card(session, user, version_id)
    return _envelope(request, data, etag=tasks._etag(data["revision"]))


@router.put("/{version_id}/role-card")
def save_role_card(
    request: Request,
    version_id: str,
    payload: SaveRoleCardRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> JSONResponse:
    data = p3.save_role_card(
        session,
        user,
        version_id,
        payload.role_card,
        expected_revision=tasks.parse_if_match(if_match),
    )
    return _envelope(request, data, etag=tasks._etag(data["revision"]))


@router.post("/{version_id}/role-candidates/{run_id}/apply")
def apply_role_candidate(
    request: Request,
    version_id: str,
    run_id: str,
    payload: ApplyRoleCandidateRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    expected = tasks.parse_if_match(if_match)
    reservation, replay = _reserve_idempotency(
        request, session, user.id, idempotency_key, payload, expected
    )
    if replay is not None:
        return replay
    data = p3.apply_role_candidate(
        session,
        user,
        version_id,
        run_id,
        payload.confirmation_id,
        expected_revision=expected,
    )
    _complete_idempotency(session, reservation, data, 200, run_id)
    return _envelope(request, data, etag=tasks._etag(data.revision))


@router.post("/{version_id}/validations", status_code=202)
def start_validation(
    request: Request,
    background: BackgroundTasks,
    version_id: str,
    _payload: EmptyRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
    settings: SettingsDependency,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    expected = tasks.parse_if_match(if_match)
    reservation, replay = _reserve_idempotency(
        request, session, user.id, idempotency_key, _payload, expected
    )
    if replay is not None:
        return replay
    run = p3.start_validation(
        session,
        user,
        version_id,
        expected_revision=expected,
        settings=settings,
    )
    data = materials.run_view(run)
    _complete_idempotency(session, reservation, data, 202, run.id)
    _start_background(request, background, p3.process_validation, run.id)
    return _envelope(request, data, status=202)


@router.post("/{version_id}/preflights")
def start_preflight(
    request: Request,
    background: BackgroundTasks,
    version_id: str,
    _payload: EmptyRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
    settings: SettingsDependency,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    expected = tasks.parse_if_match(if_match)
    reservation, replay = _reserve_idempotency(
        request, session, user.id, idempotency_key, _payload, expected
    )
    if replay is not None:
        return replay
    run, status = p3.start_preflight(
        session,
        user,
        version_id,
        expected_revision=expected,
        settings=settings,
    )
    data = materials.run_view(run)
    _complete_idempotency(session, reservation, data, status, run.id)
    if status == 202:
        _start_background(request, background, p3.process_preflight, run.id)
    return _envelope(request, data, status=status)


@router.get("/{version_id}/publish-check")
def publish_check(
    request: Request, version_id: str, session: DatabaseSession, user: TeacherUser
) -> JSONResponse:
    return _envelope(request, p3.publish_readiness(session, user, version_id))


@router.post("/{version_id}/plan-generations", status_code=202)
def start_plan_generation(
    request: Request,
    background: BackgroundTasks,
    version_id: str,
    payload: PlanGenerationRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
    settings: SettingsDependency,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    expected = tasks.parse_if_match(if_match)
    reservation, replay = _reserve_idempotency(
        request, session, user.id, idempotency_key, payload, expected
    )
    if replay is not None:
        return replay
    run = p3.start_plan_generation(
        session,
        user,
        version_id,
        expected_revision=expected,
        confirmation_id=payload.confirmation_id,
        settings=settings,
    )
    data = materials.run_view(run)
    _complete_idempotency(session, reservation, data, 202, run.id)
    _start_background(request, background, p3.process_plan_generation, run.id)
    return _envelope(request, data, status=202)


@router.post("/{version_id}/plan-generations/{run_id}/undo")
def undo_plan(
    request: Request,
    version_id: str,
    run_id: str,
    _payload: EmptyRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    expected = tasks.parse_if_match(if_match)
    reservation, replay = _reserve_idempotency(
        request, session, user.id, idempotency_key, _payload, expected
    )
    if replay is not None:
        return replay
    data = p3.undo_plan(
        session,
        user,
        version_id,
        run_id,
        expected_revision=expected,
    )
    _complete_idempotency(session, reservation, data, 200, run_id)
    return _envelope(request, data, etag=tasks._etag(data.revision))


@router.post("/{version_id}/confirmations", status_code=201)
def create_confirmation(
    request: Request,
    version_id: str,
    payload: CreateConfirmationRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
    settings: SettingsDependency,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    expected = tasks.parse_if_match(if_match)
    reservation, replay = _reserve_idempotency(
        request, session, user.id, idempotency_key, payload, expected
    )
    if replay is not None:
        return replay
    data = p3.create_confirmation(
        session,
        user,
        version_id,
        payload,
        expected_revision=expected,
        settings=settings,
    )
    _complete_idempotency(session, reservation, data, 201, data.confirmation_id)
    return _envelope(request, data, status=201)


@runs_router.post("/{run_id}/cancel")
def cancel_run(
    request: Request,
    run_id: str,
    payload: CancelRunRequest,
    session: DatabaseSession,
    auth: CSRFProtected,
) -> JSONResponse:
    run = p3.cancel_run(session, auth[1], run_id, payload.reason)
    status = 202 if run.status == "cancelled" else 200
    return _envelope(
        request,
        {
            "runId": run.id,
            "cancelRequested": run.cancel_requested_at is not None,
            "run": materials.run_view(run),
        },
        status=status,
    )
