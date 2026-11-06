"""B01--B07 task, draft and version routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.dependencies import CSRFProtected, CurrentUser, DatabaseSession, TeacherUser
from app.core.errors import AppError
from app.db.models import User
from app.schemas.common import Envelope
from app.schemas.task_dtos import (
    CopyVersionRequest,
    CreateTaskRequest,
    PatchVersionRequest,
    TaskDetail,
    TaskListPage,
    VersionListPage,
    VersionView,
)
from app.services import tasks

router = APIRouter(prefix="/tasks", tags=["Tasks"])
versions_router = APIRouter(prefix="/versions", tags=["Tasks"])


def require_teacher_csrf(auth: CSRFProtected) -> User:
    user = auth[1]
    if user.role != "teacher" or not user.is_active:
        raise AppError("FORBIDDEN", "无权执行此操作", status_code=403)
    return user


TeacherCSRF = Annotated[User, Depends(require_teacher_csrf)]


def _envelope(
    request: Request, data: object, *, status: int = 200, etag: str | None = None
) -> JSONResponse:
    body = {"data": jsonable_encoder(data), "requestId": request.state.request_id}
    headers = {"X-Request-ID": request.state.request_id}
    if etag is not None:
        headers["ETag"] = etag
    return JSONResponse(status_code=status, content=body, headers=headers)


def _service_result(request: Request, result: tasks.ServiceResult) -> JSONResponse:
    # Idempotency stores only the data object.  The request envelope is rebuilt so
    # every replay receives this request's fresh requestId.
    return _envelope(request, result.data, status=result.status)


@router.post("", status_code=201)
def create_task(
    request: Request,
    payload: CreateTaskRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    # Settings is attached by create_app; accepting it as a plain parameter would
    # make FastAPI treat it as a request body, so read the application state here.
    config = request.app.state.settings
    result = tasks.create_task(
        session,
        user,
        payload,
        settings=config,
        path=request.url.path,
        idempotency_key=idempotency_key,
    )
    return _service_result(request, result)


@router.get("", response_model=Envelope[TaskListPage])
def list_tasks(
    request: Request,
    session: DatabaseSession,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> Envelope[TaskListPage]:
    data = tasks.list_tasks(session, user, limit=limit, cursor=cursor, status=status)
    return Envelope(data=data, request_id=request.state.request_id)


@router.get("/{task_id}", response_model=Envelope[TaskDetail])
def get_task(
    request: Request,
    task_id: str,
    session: DatabaseSession,
    user: CurrentUser,
) -> Envelope[TaskDetail]:
    data = tasks.get_task(session, user, task_id)
    return Envelope(data=data, request_id=request.state.request_id)


@router.get("/{task_id}/versions", response_model=Envelope[VersionListPage])
def list_versions(
    request: Request,
    task_id: str,
    session: DatabaseSession,
    user: TeacherUser,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> Envelope[VersionListPage]:
    data = tasks.list_versions(session, user, task_id, limit=limit, cursor=cursor)
    return Envelope(data=data, request_id=request.state.request_id)


@router.post("/{task_id}/versions", status_code=201)
def copy_version(
    request: Request,
    task_id: str,
    payload: CopyVersionRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    result = tasks.copy_version(
        session,
        user,
        task_id,
        payload,
        path=request.url.path,
        idempotency_key=idempotency_key,
    )
    return _service_result(request, result)


@versions_router.get("/{version_id}", response_model=Envelope[VersionView])
def get_version(
    request: Request,
    version_id: str,
    session: DatabaseSession,
    user: TeacherUser,
) -> JSONResponse:
    data = tasks.get_version(session, user, version_id)
    return _envelope(request, data, etag=tasks._etag(data.revision))


@versions_router.patch("/{version_id}", response_model=Envelope[VersionView])
def patch_version(
    request: Request,
    version_id: str,
    payload: PatchVersionRequest,
    session: DatabaseSession,
    user: TeacherCSRF,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> JSONResponse:
    expected = tasks.parse_if_match(if_match)
    data = tasks.patch_version(session, user, version_id, payload, expected_revision=expected)
    return _envelope(request, data, etag=tasks._etag(data.revision))
