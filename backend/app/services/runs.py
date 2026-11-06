"""Shared P2--P4 Run authorization, cancellation, and event access."""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from app.core.errors import AppError
from app.db.models import AgentRun, Message, RoleSession, RunEvent, Task, TaskMember, User
from app.schemas.material_dtos import RunView
from app.services import dialogue, materials, p3
from app.workflows.runtime import WorkflowRuntime

TERMINAL = {"completed", "failed", "cancelled", "waiting_confirmation"}


def authorize(session: Session, user: User, run_id: str) -> tuple[AgentRun, Task]:
    run = session.get(AgentRun, run_id)
    if run is None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    task = session.get(Task, run.task_id)
    if task is None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    if task.owner_id == user.id and user.role == "teacher":
        return run, task
    if run.actor_id != user.id:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    if run.session_id is not None:
        role_session = session.get(RoleSession, run.session_id)
        if role_session is None or role_session.owner_id != user.id:
            raise AppError("NOT_FOUND", "资源不存在", 404)
        if role_session.mode == "student" and (
            task.status != "active" or session.get(TaskMember, (task.id, user.id)) is None
        ):
            raise AppError("NOT_FOUND", "资源不存在", 404)
    elif user.role != "teacher":
        raise AppError("NOT_FOUND", "资源不存在", 404)
    return run, task


def get_run(session: Session, user: User, run_id: str) -> RunView:
    run, _ = authorize(session, user, run_id)
    return materials.run_view(run)


def list_events(
    session: Session, user: User, run_id: str, after_seq: int
) -> tuple[list[tuple[int, str, dict[str, Any]]], bool]:
    run, _ = authorize(session, user, run_id)
    rows = session.exec(
        select(RunEvent)
        .where(RunEvent.run_id == run.id, RunEvent.seq > after_seq)
        .order_by(RunEvent.seq)
    ).all()
    events = []
    for row in rows:
        payload = json.loads(row.payload_json)
        events.append((row.seq, row.event_type, payload))
    return events, run.status in TERMINAL


def cancel(
    session: Session, user: User, run_id: str, reason: str | None, runtime: WorkflowRuntime
) -> AgentRun:
    run, _ = authorize(session, user, run_id)
    if run.status not in {"running", "waiting_confirmation"}:
        return run
    if run.kind not in {"chat", "summary"}:
        row = p3.cancel_run(session, user, run_id, reason)
        session.commit()
        return row
    now = dialogue._now()
    run.cancel_requested_at = run.cancel_requested_at or now
    session.commit()
    runtime.cancel(run.id)
    dialogue._terminal(session.get_bind(), run.id, status="cancelled", reason=reason)
    session.expire_all()
    return session.get(AgentRun, run.id)


def retry(
    session: Session, user: User, run_id: str, settings, *, path: str, idempotency_key: str | None
):
    return dialogue.retry_chat(
        session, user, run_id, settings, path=path, idempotency_key=idempotency_key
    )


def public_partial_message(session: Session, run: AgentRun) -> str | None:
    if run.output_message_id is None:
        return None
    message = session.get(Message, run.output_message_id)
    return message.id if message is not None and message.status == "partial" else None
