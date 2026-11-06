"""Reusable object authorization helpers for business routes.

The helpers intentionally distinguish an invisible object (404) from a visible
object used by the wrong role (403). They accept already-loaded rows so future
routes can choose their own query and avoid leaking existence through lookups.
"""

from __future__ import annotations

from sqlmodel import Session

from app.api.dependencies import Authenticated
from app.core.errors import AppError
from app.db.models import RoleSession, Task, TaskMember, User


def require_teacher(user_auth: Authenticated) -> User:
    _, user = user_auth
    if user.role != "teacher":
        raise AppError("FORBIDDEN", "无权执行此操作", status_code=403)
    return user


def require_task_owner(task: Task, user_auth: Authenticated) -> Task:
    _, user = user_auth
    if task.owner_id != user.id:
        raise AppError("NOT_FOUND", "资源不存在", status_code=404)
    return task


def require_task_member(task: Task, user_auth: Authenticated, db: Session) -> TaskMember:
    _, user = user_auth
    member = db.get(TaskMember, (task.id, user.id))
    if member is None:
        raise AppError("NOT_FOUND", "资源不存在", status_code=404)
    return member


def require_session_owner(role_session: RoleSession, user_auth: Authenticated) -> RoleSession:
    _, user = user_auth
    if role_session.owner_id != user.id:
        raise AppError("NOT_FOUND", "资源不存在", status_code=404)
    return role_session


def task_owner_or_member(task: Task, user_auth: Authenticated, db: Session) -> User:
    """Authorize either owner or active member and return the authenticated user."""
    _, user = user_auth
    if task.owner_id == user.id:
        return user
    if db.get(TaskMember, (task.id, user.id)) is not None:
        return user
    raise AppError("NOT_FOUND", "资源不存在", status_code=404)
