"""Task/version transaction services for B01--B07.

The service owns authorization checks, transaction boundaries, optimistic revision
updates, and serialization.  Model calls, publication, archives, sources and
sessions intentionally do not belong here.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, or_, update
from sqlmodel import Session, select

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models import RoleCard, Task, TaskMember, TaskVersion, VersionSource
from app.db.models import User as UserRow
from app.schemas.task_dtos import (
    CopyVersionRequest,
    CreateTaskRequest,
    PatchVersionRequest,
    TaskDetail,
    TaskListItem,
    TaskListPage,
    VersionListPage,
    VersionSummary,
    VersionView,
)
from app.services import idempotency


@dataclass(frozen=True)
class ServiceResult:
    data: Any
    status: int = 200
    replay_status: int | None = None
    replay_data: dict[str, Any] | None = None


def now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load_object(value: str, default: Any) -> Any:
    try:
        loaded = json.loads(value)
    except (TypeError, ValueError):
        return default
    return loaded


def _cursor_encode(created_at: str, row_id: str) -> str:
    raw = _json({"v": 1, "createdAt": created_at, "id": row_id}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _cursor_decode(cursor: str | None) -> tuple[str, str] | None:
    if cursor is None:
        return None
    if len(cursor) > 512:
        raise AppError("VALIDATION_ERROR", "cursor 无效", 422)
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        if value.get("v") != 1 or not isinstance(value.get("createdAt"), str):
            raise ValueError
        row_id = value.get("id")
        if not isinstance(row_id, str) or not row_id or len(row_id) > 128:
            raise ValueError
        return value["createdAt"], row_id
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        raise AppError("VALIDATION_ERROR", "cursor 无效", 422) from None


def _etag(revision: int) -> str:
    return f'"rev-{revision}"'


def parse_if_match(value: str | None) -> int:
    if value is None:
        raise AppError("PRECONDITION_REQUIRED", "需要 If-Match", 428)
    candidate = value.strip()
    if not re.fullmatch(r'"rev-[1-9][0-9]*"', candidate):
        raise AppError("PRECONDITION_REQUIRED", "If-Match 格式无效", 428)
    try:
        revision = int(candidate[5:-1])
    except ValueError:
        raise AppError("PRECONDITION_REQUIRED", "If-Match 格式无效", 428) from None
    return revision


def _ensure_user(user: UserRow, role: str | None = None) -> None:
    if not user.is_active or (role is not None and user.role != role):
        raise AppError("FORBIDDEN", "无权执行此操作", 403)


def _task_for_owner(session: Session, task_id: str, user: UserRow) -> Task:
    _ensure_user(user, "teacher")
    task = session.get(Task, task_id)
    if task is None or task.owner_id != user.id:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    return task


def _student_can_access(session: Session, task: Task, user: UserRow) -> bool:
    if user.role != "student" or not user.is_active:
        return False
    if task.status != "active" or task.current_published_version_id is None:
        return False
    return session.get(TaskMember, (task.id, user.id)) is not None


def _brief_data(raw: dict[str, Any] | None, settings: Settings | None = None) -> dict[str, Any]:
    result = dict(raw or {})
    if settings is not None:
        result.setdefault("subject", settings.default_subject)
        result.setdefault("grade", settings.default_grade)
    return result


def _missing_questions(brief: dict[str, Any]) -> tuple[list[str], list[str]]:
    required = (
        ("topicName", "请补充探究主题"),
        ("background", "请补充主题背景"),
        ("coreQuestion", "请明确核心问题"),
    )
    missing = [field for field, _ in required if not brief.get(field)]
    questions = [question for field, question in required if field in missing][:3]
    return missing, questions


def _role_card(session: Session, version_id: str) -> dict[str, Any] | None:
    row = session.exec(select(RoleCard).where(RoleCard.version_id == version_id)).first()
    if row is None:
        return None
    card = _load_object(row.card_json, {})
    if not isinstance(card, dict):
        card = {}
    return {"roleId": row.id, **card}


def _source_ids(session: Session, version_id: str) -> list[str]:
    rows = session.exec(
        select(VersionSource.source_id)
        .where(VersionSource.version_id == version_id)
        .order_by(VersionSource.source_id)
    ).all()
    return list(rows)


def version_view(
    session: Session, version: TaskVersion, *, include_draft: bool = True
) -> VersionView:
    brief = _load_object(version.brief_json, {})
    if not isinstance(brief, dict):
        brief = {}
    question_plan = _load_object(version.question_plan_json, [])
    if not isinstance(question_plan, list):
        question_plan = []
    manual_fields = _load_object(version.manual_fields_json, [])
    if not isinstance(manual_fields, list):
        manual_fields = []
    generation_meta = _load_object(version.generation_meta_json, {})
    if not isinstance(generation_meta, dict):
        generation_meta = {}
    missing, questions = _missing_questions(brief)
    generated_missing = generation_meta.get("missingFields", [])
    generated_questions = generation_meta.get("nextQuestions", [])
    if isinstance(generated_missing, list):
        missing = list(
            dict.fromkeys(
                [*missing, *(str(item) for item in generated_missing if str(item).strip())]
            )
        )[:3]
    if isinstance(generated_questions, list):
        questions = list(
            dict.fromkeys(
                [*questions, *(str(item) for item in generated_questions if str(item).strip())]
            )
        )[:3]
    return VersionView(
        id=version.id,
        task_id=version.task_id,
        version_no=version.version_no,
        revision=version.revision,
        status=version.status,
        from_version_id=version.from_version_id,
        teaching_intent=version.teaching_intent,
        brief=brief,
        question_plan=question_plan,
        role_card=_role_card(session, version.id),
        source_ids=_source_ids(session, version.id),
        manual_fields=manual_fields if include_draft else [],
        generation_meta=generation_meta if include_draft else {},
        validation_status=version.validation_status,
        validated_revision=version.validated_revision if include_draft else None,
        preview_revision=version.preview_revision if include_draft else None,
        created_at=version.created_at,
        updated_at=version.updated_at,
        published_at=version.published_at,
        missing_fields=missing,
        next_questions=questions,
    )


def version_summary(version: TaskVersion) -> VersionSummary:
    return VersionSummary(
        id=version.id,
        task_id=version.task_id,
        version_no=version.version_no,
        revision=version.revision,
        status=version.status,
        teaching_intent=version.teaching_intent,
        created_at=version.created_at,
        updated_at=version.updated_at,
        published_at=version.published_at,
        from_version_id=version.from_version_id,
    )


def _public_brief(version: TaskVersion | None) -> dict[str, Any] | None:
    if version is None:
        return None
    brief = _load_object(version.brief_json, {})
    if not isinstance(brief, dict):
        return None
    # Public task pages do not expose teacher provenance or incomplete internals.
    fields = (
        "topicName",
        "background",
        "subject",
        "grade",
        "learningGoals",
        "coreQuestion",
        "isHistoricalTopic",
        "timeAnchor",
        "region",
        "roleType",
        "roleName",
        "expectedOutcome",
    )
    return {field: brief[field] for field in fields if field in brief}


def _public_role(session: Session, version: TaskVersion | None) -> dict[str, Any] | None:
    if version is None:
        return None
    card = _role_card(session, version.id)
    if card is None:
        return None
    fields = (
        "roleId",
        "name",
        "roleType",
        "identityDescription",
        "historicalPeriod",
        "timeAnchor",
        "region",
        "position",
        "speechStyle",
        "openingMessage",
        "recommendedQuestions",
        "learningDimension",
    )
    return {field: card[field] for field in fields if field in card}


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump(by_alias=True))
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value


def _idempotency_result(
    reservation: idempotency.Reservation,
) -> ServiceResult | None:
    if reservation.replay is None:
        return None
    return ServiceResult(
        data=reservation.replay.body,
        status=reservation.replay.status,
        replay_status=reservation.replay.status,
        replay_data=reservation.replay.body,
    )


def _finish_idempotency(
    session: Session,
    reservation: idempotency.Reservation,
    data: Any,
    status: int,
    resource_id: str | None = None,
) -> None:
    serialized = _to_jsonable(data)
    idempotency.complete(
        session,
        reservation,
        status=status,
        body=serialized,
        resource_id=resource_id,
    )


def create_task(
    session: Session,
    user: UserRow,
    payload: CreateTaskRequest,
    *,
    settings: Settings,
    path: str,
    idempotency_key: str | None,
) -> ServiceResult:
    _ensure_user(user, "teacher")
    body = payload.model_dump(by_alias=True, exclude_unset=True)
    reservation = idempotency.begin(
        session,
        user_id=user.id,
        method="POST",
        path=path,
        key=idempotency_key,
        digest=idempotency.request_hash("POST", path, body),
    )
    replay = _idempotency_result(reservation)
    if replay is not None:
        return replay

    supplied = body.get("brief")
    brief = _brief_data(supplied if isinstance(supplied, dict) else None, settings)
    task_id = str(uuid4())
    version_id = str(uuid4())
    now = now_text()
    task = Task(
        id=task_id,
        owner_id=user.id,
        status="active",
        row_version=1,
        current_published_version_id=None,
        created_at=now,
        updated_at=now,
    )
    version = TaskVersion(
        id=version_id,
        task_id=task_id,
        version_no=1,
        revision=1,
        status="draft",
        from_version_id=None,
        teaching_intent=body.get("teachingIntent", "") or "",
        manual_fields_json="[]",
        generation_meta_json="{}",
        brief_json=_json(brief),
        question_plan_json="[]",
        validation_status="stale",
        validated_revision=None,
        preview_revision=None,
        content_hash=None,
        published_at=None,
        published_by=None,
        created_at=now,
        updated_at=now,
    )
    session.add(task)
    session.add(version)
    try:
        session.flush()
        result = {
            "taskId": task.id,
            "taskRevision": task.row_version,
            "draft": version_view(session, version),
        }
        _finish_idempotency(session, reservation, result, 201, task.id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return ServiceResult(data=result, status=201)


def list_tasks(
    session: Session,
    user: UserRow,
    *,
    limit: int,
    cursor: str | None,
    status: str | None,
) -> TaskListPage:
    _ensure_user(user)
    if not 1 <= limit <= 100:
        raise AppError("VALIDATION_ERROR", "limit 必须在 1 到 100 之间", 422)
    marker = _cursor_decode(cursor)
    statement = select(Task)
    if user.role == "teacher":
        statement = statement.where(Task.owner_id == user.id)
        if status is not None:
            if status not in {"active", "archived"}:
                raise AppError("VALIDATION_ERROR", "status 无效", 422)
            statement = statement.where(Task.status == status)
    elif user.role == "student":
        statement = statement.where(
            Task.id.in_(select(TaskMember.task_id).where(TaskMember.user_id == user.id)),
            Task.status == "active",
            Task.current_published_version_id.is_not(None),
        )
    else:
        raise AppError("FORBIDDEN", "无权执行此操作", 403)
    if marker is not None:
        created_at, row_id = marker
        statement = statement.where(
            or_(Task.created_at < created_at, and_(Task.created_at == created_at, Task.id < row_id))
        )
    rows = session.exec(
        statement.order_by(Task.created_at.desc(), Task.id.desc()).limit(limit + 1)
    ).all()
    # SQLModel's Session.exec may return scalar rows or Row objects when a
    # concurrent auth/query extension adds a join; normalize defensively.
    rows = [
        row[0] if not isinstance(row, Task) and hasattr(row, "__getitem__") else row for row in rows
    ]
    has_next = len(rows) > limit
    rows = rows[:limit]
    items: list[TaskListItem] = []
    for task in rows:
        version_id = task.current_published_version_id
        version = session.get(TaskVersion, version_id) if version_id else None
        if version is None:
            version = session.exec(
                select(TaskVersion)
                .where(TaskVersion.task_id == task.id, TaskVersion.status == "draft")
                .order_by(TaskVersion.version_no.desc())
            ).first()
        if version is not None and not isinstance(version, TaskVersion):
            version = version[0]
        brief = _load_object(version.brief_json, {}) if version else {}
        topic = brief.get("topicName", "") if isinstance(brief, dict) else ""
        items.append(
            TaskListItem(
                task_id=task.id,
                topic_name=topic if isinstance(topic, str) else "",
                status=task.status,
                current_published_version_id=task.current_published_version_id,
            )
        )
    next_cursor = _cursor_encode(rows[-1].created_at, rows[-1].id) if has_next and rows else None
    return TaskListPage(items=items, next_cursor=next_cursor)


def get_task(session: Session, user: UserRow, task_id: str) -> TaskDetail:
    _ensure_user(user)
    task = session.get(Task, task_id)
    if task is None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    if user.role == "teacher":
        if task.owner_id != user.id:
            raise AppError("NOT_FOUND", "资源不存在", 404)
    elif not _student_can_access(session, task, user):
        raise AppError("NOT_FOUND", "资源不存在", 404)

    published = (
        session.get(TaskVersion, task.current_published_version_id)
        if task.current_published_version_id
        else None
    )
    draft = session.exec(
        select(TaskVersion).where(TaskVersion.task_id == task.id, TaskVersion.status == "draft")
    ).first()
    teacher = user.role == "teacher"
    return TaskDetail(
        id=task.id,
        status=task.status,
        task_revision=task.row_version,
        current_published_version_id=task.current_published_version_id,
        draft_version_id=draft.id if teacher and draft else None,
        public_brief=_public_brief(published or (draft if teacher else None)),
        public_role=_public_role(session, published) if published else None,
    )


def list_versions(
    session: Session,
    user: UserRow,
    task_id: str,
    *,
    limit: int,
    cursor: str | None,
) -> VersionListPage:
    task = _task_for_owner(session, task_id, user)
    if not 1 <= limit <= 100:
        raise AppError("VALIDATION_ERROR", "limit 必须在 1 到 100 之间", 422)
    marker = _cursor_decode(cursor)
    statement = select(TaskVersion).where(TaskVersion.task_id == task.id)
    if marker is not None:
        created_at, row_id = marker
        statement = statement.where(
            or_(
                TaskVersion.created_at < created_at,
                and_(TaskVersion.created_at == created_at, TaskVersion.id < row_id),
            )
        )
    rows = session.exec(
        statement.order_by(TaskVersion.created_at.desc(), TaskVersion.id.desc()).limit(limit + 1)
    ).all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    # B04's data shape is a page of Version summaries, not task rows.  Keep the
    # page DTO local to avoid changing the generic public pagination contract.
    next_cursor = _cursor_encode(rows[-1].created_at, rows[-1].id) if has_next and rows else None
    return VersionListPage(items=[version_summary(row) for row in rows], next_cursor=next_cursor)


def get_version(session: Session, user: UserRow, version_id: str) -> VersionView:
    _ensure_user(user, "teacher")
    version = session.get(TaskVersion, version_id)
    if version is None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    task = session.get(Task, version.task_id)
    if task is None or task.owner_id != user.id:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    return version_view(session, version)


def copy_version(
    session: Session,
    user: UserRow,
    task_id: str,
    payload: CopyVersionRequest,
    *,
    path: str,
    idempotency_key: str | None,
) -> ServiceResult:
    task = _task_for_owner(session, task_id, user)
    body = payload.model_dump(by_alias=True)
    reservation = idempotency.begin(
        session,
        user_id=user.id,
        method="POST",
        path=path,
        key=idempotency_key,
        digest=idempotency.request_hash("POST", path, body),
    )
    replay = _idempotency_result(reservation)
    if replay is not None:
        return replay

    # Force a write lock on the task row before checking the conditional draft
    # invariant. SQLite serializes writers; the unique partial index is the final
    # backstop if another process races this transaction.
    session.execute(update(Task).where(Task.id == task.id).values(updated_at=task.updated_at))
    source = session.get(TaskVersion, payload.from_version_id)
    if source is None or source.task_id != task.id:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    if source.status != "published":
        raise AppError("VERSION_NOT_PUBLISHED", "只能从已发布版本复制", 409)
    existing = session.exec(
        select(TaskVersion).where(TaskVersion.task_id == task.id, TaskVersion.status == "draft")
    ).first()
    if existing is not None:
        raise AppError("DRAFT_EXISTS", "该任务已有草稿", 409)

    max_version = session.exec(
        select(TaskVersion.version_no)
        .where(TaskVersion.task_id == task.id)
        .order_by(TaskVersion.version_no.desc())
    ).first()
    version_no = (max_version or 0) + 1
    now = now_text()
    version = TaskVersion(
        id=str(uuid4()),
        task_id=task.id,
        version_no=version_no,
        revision=1,
        status="draft",
        from_version_id=source.id,
        teaching_intent=source.teaching_intent,
        manual_fields_json=source.manual_fields_json,
        generation_meta_json=source.generation_meta_json,
        brief_json=source.brief_json,
        question_plan_json=source.question_plan_json,
        validation_status="stale",
        validated_revision=None,
        preview_revision=None,
        content_hash=None,
        published_at=None,
        published_by=None,
        created_at=now,
        updated_at=now,
    )
    session.add(version)
    source_card = session.exec(select(RoleCard).where(RoleCard.version_id == source.id)).first()
    if source_card is not None:
        session.add(
            RoleCard(
                id=str(uuid4()),
                version_id=version.id,
                card_json=source_card.card_json,
                edited_by=user.id,
                created_at=now,
                updated_at=now,
            )
        )
    for source_id in _source_ids(session, source.id):
        session.add(
            VersionSource(
                task_id=task.id,
                version_id=version.id,
                source_id=source_id,
                created_at=now,
            )
        )
    try:
        session.flush()
        result = version_view(session, version)
        _finish_idempotency(session, reservation, result, 201, version.id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return ServiceResult(data=result, status=201)


def patch_version(
    session: Session,
    user: UserRow,
    version_id: str,
    payload: PatchVersionRequest,
    *,
    expected_revision: int,
) -> VersionView:
    _ensure_user(user, "teacher")
    version = session.get(TaskVersion, version_id)
    if version is None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    task = session.get(Task, version.task_id)
    if task is None or task.owner_id != user.id:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    if version.status != "draft":
        raise AppError("VERSION_IMMUTABLE", "已发布版本不可修改", 409)
    if version.revision != expected_revision:
        raise AppError(
            "REVISION_CONFLICT",
            "内容已变化，请重新载入",
            412,
            details={"currentRevision": version.revision},
        )

    changed = payload.model_dump(by_alias=True, exclude_unset=True)
    brief = _load_object(version.brief_json, {})
    if not isinstance(brief, dict):
        brief = {}
    manual = _load_object(version.manual_fields_json, [])
    if not isinstance(manual, list):
        manual = []
    if "teachingIntent" in changed:
        version.teaching_intent = changed["teachingIntent"] or ""
        if "teachingIntent" not in manual:
            manual.append("teachingIntent")
    brief_patch = changed.get("brief")
    if isinstance(brief_patch, dict):
        for field, value in brief_patch.items():
            brief[field] = value
            marker = f"brief.{field}"
            if marker not in manual:
                manual.append(marker)
    if "questionPlan" in changed:
        question_plan = changed["questionPlan"]
        version.question_plan_json = _json(question_plan if question_plan is not None else [])
        if "questionPlan" not in manual:
            manual.append("questionPlan")

    # The conditional UPDATE is the optimistic-lock gate. It also avoids an ORM
    # stale identity-map write overwriting a concurrent successful patch.
    new_revision = expected_revision + 1
    now = now_text()
    values = {
        "revision": new_revision,
        "teaching_intent": version.teaching_intent,
        "brief_json": _json(brief),
        "question_plan_json": version.question_plan_json,
        "manual_fields_json": _json(manual),
        "validation_status": "stale",
        "validated_revision": None,
        "preview_revision": None,
        "content_hash": None,
        "generation_meta_json": "{}",
        "updated_at": now,
    }
    result = session.execute(
        update(TaskVersion)
        .where(
            TaskVersion.id == version.id,
            TaskVersion.status == "draft",
            TaskVersion.revision == expected_revision,
        )
        .values(**values)
    )
    if result.rowcount != 1:
        session.rollback()
        current = session.get(TaskVersion, version.id)
        current_revision = current.revision if current else expected_revision
        raise AppError(
            "REVISION_CONFLICT",
            "内容已变化，请重新载入",
            412,
            details={"currentRevision": current_revision},
        )
    session.commit()
    refreshed = session.get(TaskVersion, version.id)
    if refreshed is None:  # pragma: no cover - protected by the UPDATE predicate
        raise AppError("NOT_FOUND", "资源不存在", 404)
    return version_view(session, refreshed)
