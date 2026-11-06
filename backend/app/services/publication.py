"""P5 publication, membership replacement, and task archive transactions."""

from __future__ import annotations

from uuid import uuid4

from sqlmodel import Session, select

from app.core.errors import AppError
from app.db.models import (
    AgentRun,
    Confirmation,
    ReviewRecord,
    Task,
    TaskMember,
    TaskVersion,
    User,
)
from app.schemas.p5_dtos import PublishResult, TaskStatusResult
from app.services import p3


def _owner_task(session: Session, user: User, task_id: str) -> Task:
    task = session.get(Task, task_id)
    if user.role != "teacher" or not user.is_active:
        raise AppError("FORBIDDEN", "无权执行此操作", 403)
    if task is None or task.owner_id != user.id:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    return task


def _audit(
    session: Session,
    *,
    task: Task,
    version: TaskVersion,
    actor_id: str,
    action: str,
    details: dict[str, object],
) -> None:
    session.add(
        ReviewRecord(
            id=str(uuid4()),
            task_id=task.id,
            version_id=version.id,
            version_revision=version.revision,
            kind="business_audit",
            session_id=None,
            run_id=None,
            message_id=None,
            block_index=None,
            actor_id=actor_id,
            passed=1,
            result_json=p3._json({"action": action, **details}),
            issues_json="[]",
            created_at=p3._now(),
        )
    )


def publish_version(
    session: Session,
    user: User,
    version_id: str,
    confirmation_id: str,
    *,
    expected_revision: int,
) -> tuple[PublishResult, list[str]]:
    task, version = p3._owner_draft(session, user, version_id)
    p3._check_revision(version, expected_revision)
    readiness = p3.publish_readiness(session, user, version.id)
    if version.validation_status != "valid" or version.validated_revision != version.revision:
        raise AppError("VALIDATION_REQUIRED", "角色一致性检查尚未通过", 409)
    if any(source.status != "ready" for source in p3._linked_sources(session, version)):
        raise AppError("SOURCE_NOT_READY", "参考资料尚未准备完成", 409)
    if not readiness["ready"]:
        raise AppError("PREFLIGHT_REQUIRED", "当前方案尚未通过发布前检查", 409)
    confirmation = p3._valid_confirmation(
        session, user, version, confirmation_id, "publish_version", task.row_version
    )
    payload = p3._load(confirmation.payload_json, {})
    student_ids = payload.get("studentIds")
    if not isinstance(student_ids, list) or any(not isinstance(item, str) for item in student_ids):
        raise AppError("CONFIRMATION_STALE", "发布对象确认无效", 409)
    normalized_ids = sorted(set(student_ids))
    students = session.exec(select(User).where(User.id.in_(normalized_ids))).all()
    if len(students) != len(normalized_ids) or any(
        row.role != "student" or not row.is_active for row in students
    ):
        raise AppError("CONFIRMATION_STALE", "发布对象已变化，请重新确认", 409)
    current_hash = p3.content_hash(session, version)
    expected_content = p3._confirmation_content(
        "publish_version", version, task, {"studentIds": normalized_ids}, current_hash
    )
    if confirmation.content_hash != expected_content or confirmation.payload_hash != p3._hash(
        {"studentIds": normalized_ids}
    ):
        raise AppError("CONFIRMATION_STALE", "方案或发布对象已变化，请重新确认", 409)

    current_members = set(
        session.exec(select(TaskMember.user_id).where(TaskMember.task_id == task.id)).all()
    )
    removed = sorted(current_members - set(normalized_ids))
    for member in session.exec(select(TaskMember).where(TaskMember.task_id == task.id)).all():
        session.delete(member)
    now = p3._now()
    for student_id in normalized_ids:
        session.add(
            TaskMember(
                task_id=task.id,
                user_id=student_id,
                granted_by=user.id,
                created_at=now,
            )
        )
    cancelled_run_ids: list[str] = []
    if removed:
        active_runs = session.exec(
            select(AgentRun).where(
                AgentRun.task_id == task.id,
                AgentRun.actor_id.in_(removed),
                AgentRun.status == "running",
            )
        ).all()
        for run in active_runs:
            run.cancel_requested_at = now
            cancelled_run_ids.append(run.id)

    confirmation.consumed_at = now
    version.status = "published"
    version.content_hash = current_hash
    version.published_at = now
    version.published_by = user.id
    version.updated_at = now
    task.current_published_version_id = version.id
    task.row_version += 1
    task.updated_at = now
    _audit(
        session,
        task=task,
        version=version,
        actor_id=user.id,
        action="publish_version",
        details={"studentCount": len(normalized_ids), "contentHash": current_hash},
    )
    session.flush()
    return (
        PublishResult(
            task_id=task.id,
            version_id=version.id,
            version_no=version.version_no,
            status="published",
            published_at=now,
            task_revision=task.row_version,
        ),
        cancelled_run_ids,
    )


def archive_task(
    session: Session,
    user: User,
    task_id: str,
    confirmation_id: str,
    expected_task_revision: int,
) -> tuple[TaskStatusResult, list[str]]:
    task = _owner_task(session, user, task_id)
    if task.status != "active":
        raise AppError("TASK_ARCHIVED", "任务已归档", 409)
    if task.row_version != expected_task_revision:
        raise AppError("TASK_REVISION_CONFLICT", "任务状态已变化，请重新载入", 409)
    confirmation = session.get(Confirmation, confirmation_id)
    if (
        confirmation is None
        or confirmation.actor_id != user.id
        or confirmation.task_id != task.id
        or confirmation.action != "archive_task"
    ):
        raise AppError("CONFIRMATION_REQUIRED", "需要确认归档操作", 409)
    if confirmation.consumed_at is not None:
        raise AppError("CONFIRMATION_STALE", "确认已经使用", 409)
    now = p3._now()
    if confirmation.expires_at <= now:
        raise AppError("CONFIRMATION_EXPIRED", "确认已过期，请重新确认", 409)
    expected_hash = p3._hash({"taskId": task.id, "taskRevision": task.row_version})
    if confirmation.task_revision != task.row_version or confirmation.content_hash != expected_hash:
        raise AppError("CONFIRMATION_STALE", "任务状态已变化，请重新确认", 409)
    version = session.get(TaskVersion, confirmation.version_id)
    if version is None:
        raise AppError("CONFIRMATION_STALE", "确认定位的版本不存在", 409)
    run_ids: list[str] = []
    for run in session.exec(
        select(AgentRun).where(AgentRun.task_id == task.id, AgentRun.status == "running")
    ).all():
        run.cancel_requested_at = now
        run_ids.append(run.id)
    confirmation.consumed_at = now
    task.status = "archived"
    task.archived_at = now
    task.row_version += 1
    task.updated_at = now
    _audit(
        session,
        task=task,
        version=version,
        actor_id=user.id,
        action="archive_task",
        details={"previousTaskRevision": expected_task_revision},
    )
    session.flush()
    return TaskStatusResult(
        task_id=task.id, status="archived", task_revision=task.row_version
    ), run_ids


def restore_task(
    session: Session, user: User, task_id: str, expected_task_revision: int
) -> TaskStatusResult:
    task = _owner_task(session, user, task_id)
    if task.row_version != expected_task_revision:
        raise AppError("TASK_REVISION_CONFLICT", "任务状态已变化，请重新载入", 409)
    if task.status != "archived":
        return TaskStatusResult(task_id=task.id, status="active", task_revision=task.row_version)
    version_id = task.current_published_version_id
    if version_id is None:
        version = session.exec(
            select(TaskVersion)
            .where(TaskVersion.task_id == task.id)
            .order_by(TaskVersion.version_no.desc())
        ).first()
    else:
        version = session.get(TaskVersion, version_id)
    if version is None:
        raise AppError("DATA_INTEGRITY_ERROR", "任务版本不存在", 500)
    old_revision = task.row_version
    now = p3._now()
    task.status = "active"
    task.archived_at = None
    task.row_version += 1
    task.updated_at = now
    _audit(
        session,
        task=task,
        version=version,
        actor_id=user.id,
        action="restore_task",
        details={"previousTaskRevision": old_revision},
    )
    session.flush()
    return TaskStatusResult(task_id=task.id, status="active", task_revision=task.row_version)
