"""Request-scoped database, authentication, and role dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session

from app.core.config import Settings
from app.db.models import LoginSession, User
from app.services.auth import current_session, validate_write_security


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


DatabaseSession = Annotated[Session, Depends(get_session)]


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


SettingsDependency = Annotated[Settings, Depends(get_settings)]


def get_current_auth(
    request: Request, session: DatabaseSession, config: SettingsDependency
) -> tuple[LoginSession, User]:
    return current_session(request, session, config)


Authenticated = Annotated[tuple[LoginSession, User], Depends(get_current_auth)]


def get_current_user(auth: Authenticated) -> User:
    return auth[1]


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_teacher(user: CurrentUser) -> User:
    from app.core.errors import AppError

    if user.role != "teacher":
        raise AppError("FORBIDDEN", "无权执行此操作", status_code=403)
    return user


TeacherUser = Annotated[User, Depends(require_teacher)]


def require_student(user: CurrentUser) -> User:
    from app.core.errors import AppError

    if user.role != "student":
        raise AppError("FORBIDDEN", "无权执行此操作", status_code=403)
    return user


StudentUser = Annotated[User, Depends(require_student)]


def require_csrf(
    request: Request,
    auth: Authenticated,
    config: SettingsDependency,
) -> tuple[LoginSession, User]:
    validate_write_security(request, config, auth[0])
    return auth


CSRFProtected = Annotated[tuple[LoginSession, User], Depends(require_csrf)]


def require_teacher_csrf(auth: CSRFProtected) -> User:
    from app.core.errors import AppError

    user = auth[1]
    if user.role != "teacher":
        raise AppError("FORBIDDEN", "无权执行此操作", status_code=403)
    return user


TeacherCSRF = Annotated[User, Depends(require_teacher_csrf)]
