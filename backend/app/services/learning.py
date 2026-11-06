"""P5 learning events, notes, immutable report snapshots, and report generation."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models import (
    AgentRun,
    Citation,
    Evidence,
    ExplorationNote,
    LearningEvent,
    LearningReport,
    Message,
    ReportCorrection,
    RoleSession,
    RunEvent,
    RunStep,
    Submission,
    Task,
    TaskMember,
    User,
)
from app.integrations.model import ModelAdapterError, StructuredModel
from app.schemas.contracts import ReportContent, ReportMetrics
from app.schemas.p5_dtos import (
    CorrectionPage,
    EndSessionResult,
    LearningEventRequest,
    LearningEventView,
    LearningReportView,
    LegacySubmissionView,
    NoteCreateRequest,
    NotePage,
    NotePatchRequest,
    NoteView,
    ReportCorrectionView,
    ReportEnvelope,
    ReportQueueResult,
)
from app.services import dialogue
from app.workflows.runtime import WorkflowRuntime

PROMPT_VERSION = "p5-learning-report-v1"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _tracking(row: RoleSession) -> str:
    if row.event_tracking_started_at is None:
        return "unavailable"
    return "complete" if row.event_tracking_started_at == row.created_at else "partial"


def _access(
    session: Session,
    user: User,
    session_id: str,
    *,
    student_write: bool = False,
    allow_historical_teacher: bool = True,
) -> tuple[Task, RoleSession]:
    role_session = session.get(RoleSession, session_id)
    task = session.get(Task, role_session.task_id) if role_session else None
    if role_session is None or task is None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    owner = role_session.owner_id == user.id
    teacher = user.role == "teacher" and task.owner_id == user.id
    if not owner and not teacher:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    if student_write:
        if user.role != "student" or not owner or role_session.mode != "student":
            raise AppError("FORBIDDEN", "无权执行此操作", 403)
        if task.status != "active" or session.get(TaskMember, (task.id, user.id)) is None:
            raise AppError("NOT_FOUND", "资源不存在", 404)
    elif owner and role_session.mode == "student" and user.role == "student":
        if task.status != "active" or session.get(TaskMember, (task.id, user.id)) is None:
            raise AppError("NOT_FOUND", "资源不存在", 404)
    elif teacher and not allow_historical_teacher and task.status != "active":
        raise AppError("TASK_ARCHIVED", "任务已归档", 409)
    return task, role_session


def _note_view(row: ExplorationNote) -> NoteView:
    return NoteView(
        id=row.id,
        session_id=row.session_id,
        message_id=row.message_id,
        block_index=row.block_index,
        original_view=row.original_view,
        type=row.answer_type,
        evidence_ids=_load(row.evidence_ids_json, []),
        judgment=row.judgment,
        credibility=row.credibility,
        limitations=row.limitations,
        row_version=row.row_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_notes(
    session: Session, user: User, session_id: str, *, limit: int, cursor: str | None
) -> NotePage:
    _, role_session = _access(session, user, session_id)
    statement = select(ExplorationNote).where(
        ExplorationNote.session_id == role_session.id, ExplorationNote.deleted_at.is_(None)
    )
    if cursor:
        statement = statement.where(ExplorationNote.id > cursor)
    rows = session.exec(statement.order_by(ExplorationNote.id).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    return NotePage(
        items=[_note_view(row) for row in rows], next_cursor=rows[-1].id if more else None
    )


def _queue_latest_live(session: Session, role_session: RoleSession) -> LearningReport | None:
    if role_session.mode != "student" or role_session.status != "active":
        return None
    return _ensure_report(session, role_session, "live")


def create_note(
    session: Session, user: User, session_id: str, payload: NoteCreateRequest
) -> NoteView:
    _, role_session = _access(session, user, session_id, student_write=True)
    if role_session.status != "active":
        raise AppError("SESSION_ENDED", "探究已经结束", 409)
    message = session.get(Message, payload.message_id)
    blocks = _load(message.blocks_json, []) if message else []
    if (
        message is None
        or message.session_id != role_session.id
        or message.speaker != "assistant"
        or message.status not in {"complete", "partial"}
        or payload.block_index >= len(blocks)
    ):
        raise AppError("NOT_FOUND", "可收藏的回答不存在", 404)
    block = blocks[payload.block_index]
    evidence_ids = [str(item) for item in block.get("evidenceIds", [])]
    now = dialogue._now()
    row = ExplorationNote(
        id=str(uuid4()),
        session_id=role_session.id,
        message_id=message.id,
        block_index=payload.block_index,
        original_view=str(block.get("text", "")),
        answer_type=str(block.get("type", "unknown")),
        evidence_ids_json=_json(evidence_ids),
        judgment=payload.judgment.strip(),
        credibility=payload.credibility,
        limitations=payload.limitations.strip(),
        row_version=1,
        deleted_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    role_session.learning_revision += 1
    role_session.updated_at = now
    session.flush()
    _queue_latest_live(session, role_session)
    return _note_view(row)


def _owned_note(session: Session, user: User, note_id: str) -> tuple[RoleSession, ExplorationNote]:
    note = session.get(ExplorationNote, note_id)
    role_session = session.get(RoleSession, note.session_id) if note else None
    if note is None or role_session is None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    _access(session, user, role_session.id, student_write=True)
    if note.deleted_at is not None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    if role_session.status != "active":
        raise AppError("SESSION_ENDED", "探究已经结束", 409)
    return role_session, note


def update_note(
    session: Session, user: User, note_id: str, payload: NotePatchRequest, expected: int
) -> NoteView:
    role_session, note = _owned_note(session, user, note_id)
    if note.row_version != expected:
        raise AppError("REVISION_CONFLICT", "摘录已变化，请重新载入", 412)
    changes = payload.model_dump(exclude_unset=True)
    changed = False
    for api_key, field in (
        ("judgment", "judgment"),
        ("credibility", "credibility"),
        ("limitations", "limitations"),
    ):
        if api_key in changes:
            value = changes[api_key]
            if isinstance(value, str) and field != "credibility":
                value = value.strip()
            if getattr(note, field) != value:
                setattr(note, field, value)
                changed = True
    if changed:
        now = dialogue._now()
        note.row_version += 1
        note.updated_at = now
        role_session.learning_revision += 1
        role_session.updated_at = now
        session.flush()
        _queue_latest_live(session, role_session)
    return _note_view(note)


def delete_note(session: Session, user: User, note_id: str, expected: int) -> None:
    role_session, note = _owned_note(session, user, note_id)
    if note.row_version != expected:
        raise AppError("REVISION_CONFLICT", "摘录已变化，请重新载入", 412)
    now = dialogue._now()
    note.deleted_at = now
    note.row_version += 1
    note.updated_at = now
    role_session.learning_revision += 1
    role_session.updated_at = now
    session.flush()
    _queue_latest_live(session, role_session)


def legacy_submission(session: Session, user: User, session_id: str) -> LegacySubmissionView | None:
    _, role_session = _access(session, user, session_id)
    row = session.exec(select(Submission).where(Submission.session_id == role_session.id)).first()
    if row is None:
        return None
    return LegacySubmissionView(
        id=row.id,
        session_id=row.session_id,
        status=row.status,
        content=_load(row.content_json, {}),
        row_version=row.row_version,
        submitted_at=row.submitted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _event_view(row: LearningEvent) -> LearningEventView:
    return LearningEventView(
        id=row.id,
        session_id=row.session_id,
        type=row.event_type,
        source_id=row.source_id,
        message_id=row.message_id,
        value=row.value,
        row_version=row.row_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def record_event(
    session: Session, user: User, session_id: str, payload: LearningEventRequest
) -> tuple[LearningEventView, int, bool]:
    _, role_session = _access(session, user, session_id, student_write=True)
    if role_session.status != "active":
        raise AppError("SESSION_ENDED", "探究已经结束", 409)
    now = dialogue._now()
    if payload.type == "source_open":
        cited = session.exec(
            select(Citation.id)
            .join(Evidence, Evidence.id == Citation.evidence_id)
            .join(Message, Message.id == Citation.message_id)
            .where(Message.session_id == role_session.id, Evidence.source_id == payload.source_id)
        ).first()
        if cited is None:
            raise AppError("NOT_FOUND", "该资料尚未在本会话中展示", 404)
        existing = session.exec(
            select(LearningEvent).where(
                LearningEvent.session_id == role_session.id,
                LearningEvent.event_type == "source_open",
                LearningEvent.source_id == payload.source_id,
            )
        ).first()
        if existing is not None:
            return _event_view(existing), 200, False
        row = LearningEvent(
            id=str(uuid4()),
            session_id=role_session.id,
            event_type="source_open",
            source_id=payload.source_id,
            message_id=None,
            value=None,
            row_version=1,
            created_at=now,
            updated_at=now,
        )
        status = 201
    else:
        message = session.get(Message, payload.message_id)
        if (
            message is None
            or message.session_id != role_session.id
            or message.speaker != "assistant"
            or message.status != "complete"
            or not message.text.strip()
        ):
            raise AppError("NOT_FOUND", "可判断的完整回答不存在", 404)
        existing = session.exec(
            select(LearningEvent).where(
                LearningEvent.session_id == role_session.id,
                LearningEvent.event_type == "stance",
                LearningEvent.message_id == message.id,
            )
        ).first()
        expected = payload.expected_row_version
        if existing is None:
            if expected != 0:
                raise AppError("EVENT_CONFLICT", "选择已变化，请重新载入", 409)
            row = LearningEvent(
                id=str(uuid4()),
                session_id=role_session.id,
                event_type="stance",
                source_id=None,
                message_id=message.id,
                value=payload.value,
                row_version=1,
                created_at=now,
                updated_at=now,
            )
            status = 201
        else:
            if expected != existing.row_version:
                raise AppError("EVENT_CONFLICT", "选择已变化，请重新载入", 409)
            if existing.value == payload.value:
                return _event_view(existing), 200, False
            existing.value = payload.value
            existing.row_version += 1
            existing.updated_at = now
            row = existing
            status = 200
    session.add(row)
    role_session.learning_revision += 1
    role_session.updated_at = now
    session.flush()
    _queue_latest_live(session, role_session)
    return _event_view(row), status, True


def _snapshot(session: Session, role_session: RoleSession) -> dict[str, object] | None:
    messages = session.exec(
        select(Message).where(Message.session_id == role_session.id).order_by(Message.seq)
    ).all()
    student = [
        {"messageId": row.id, "seq": row.seq, "text": row.text}
        for row in messages
        if row.speaker == "user" and row.text.strip()
    ]
    if not student:
        return None
    message_ids = [row.id for row in messages if row.speaker == "assistant"]
    citations_by_message: dict[str, list[dict[str, object]]] = {item: [] for item in message_ids}
    if message_ids:
        for citation, evidence in session.exec(
            select(Citation, Evidence)
            .join(Evidence, Evidence.id == Citation.evidence_id)
            .where(Citation.message_id.in_(message_ids))
        ).all():
            citations_by_message[citation.message_id].append(
                {
                    "evidenceId": evidence.id,
                    "sourceId": evidence.source_id,
                    "blockIndex": citation.block_index,
                    "quote": citation.quote,
                }
            )
    assistants = [
        {
            "messageId": row.id,
            "seq": row.seq,
            "status": row.status,
            "text": row.text,
            "blocks": _load(row.blocks_json, []),
            "citations": citations_by_message.get(row.id, []),
        }
        for row in messages
        if row.speaker == "assistant" and row.status in {"complete", "partial", "discarded"}
    ]
    events = session.exec(
        select(LearningEvent).where(LearningEvent.session_id == role_session.id)
    ).all()
    notes = session.exec(
        select(ExplorationNote).where(
            ExplorationNote.session_id == role_session.id, ExplorationNote.deleted_at.is_(None)
        )
    ).all()
    return {
        "session": _load(role_session.snapshot_json, {}),
        "studentMessages": student,
        "assistantMessages": assistants,
        "events": [
            {
                "type": row.event_type,
                "sourceId": row.source_id,
                "messageId": row.message_id,
                "value": row.value,
            }
            for row in events
        ],
        "notes": [
            {
                "messageId": row.message_id,
                "blockIndex": row.block_index,
                "originalView": row.original_view,
                "judgment": row.judgment,
                "credibility": row.credibility,
                "limitations": row.limitations,
            }
            for row in notes
        ],
        "sourceTracking": _tracking(role_session),
    }


def _ensure_report(session: Session, role_session: RoleSession, kind: str) -> LearningReport | None:
    snapshot = _snapshot(session, role_session)
    if snapshot is None:
        return None
    existing = session.exec(
        select(LearningReport).where(
            LearningReport.session_id == role_session.id,
            LearningReport.kind == kind,
            LearningReport.input_revision == role_session.learning_revision,
        )
    ).first()
    if existing is not None:
        return existing
    if kind == "final":
        final = session.exec(
            select(LearningReport).where(
                LearningReport.session_id == role_session.id, LearningReport.kind == "final"
            )
        ).first()
        if final is not None:
            return final
    if kind == "live":
        old = session.exec(
            select(LearningReport).where(
                LearningReport.session_id == role_session.id,
                LearningReport.kind == "live",
                LearningReport.status == "queued",
            )
        ).all()
        for row in old:
            row.status = "superseded"
            row.updated_at = dialogue._now()
    report_no = (
        session.exec(
            select(func.max(LearningReport.report_no)).where(
                LearningReport.session_id == role_session.id
            )
        ).one()
        or 0
    ) + 1
    now = dialogue._now()
    row = LearningReport(
        id=str(uuid4()),
        session_id=role_session.id,
        report_no=report_no,
        kind=kind,
        status="queued",
        input_revision=role_session.learning_revision,
        input_hash=_hash(snapshot),
        input_snapshot_json=_json(snapshot),
        generation_run_id=None,
        content_json=None,
        error_json=None,
        generated_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    return row


def end_session(session: Session, user: User, session_id: str) -> EndSessionResult:
    _, role_session = _access(
        session, user, session_id, student_write=role_session_mode(session, session_id) == "student"
    )
    if role_session.status == "ended":
        final = session.exec(
            select(LearningReport).where(
                LearningReport.session_id == role_session.id, LearningReport.kind == "final"
            )
        ).first()
        return EndSessionResult(
            session_id=role_session.id,
            status="ended",
            report_id=final.id if final else None,
            report_status=final.status if final else None,
        )
    if role_session.owner_id != user.id:
        raise AppError("FORBIDDEN", "无权结束该会话", 403)
    active = session.exec(
        select(AgentRun.id).where(
            AgentRun.session_id == role_session.id,
            AgentRun.status == "running",
            AgentRun.kind.in_(("chat", "summary")),
        )
    ).first()
    if active is not None:
        raise AppError("RUN_ALREADY_ACTIVE", "请先等待或停止当前回答", 409)
    has_student = session.exec(
        select(Message.id).where(Message.session_id == role_session.id, Message.speaker == "user")
    ).first()
    if role_session.mode == "student" and has_student is None:
        raise AppError("VALIDATION_ERROR", "至少表达一个问题或想法后才能结束探究", 422)
    now = dialogue._now()
    role_session.status = "ended"
    role_session.ended_at = now
    role_session.updated_at = now
    if role_session.mode == "preview":
        return EndSessionResult(session_id=role_session.id, status="ended")
    role_session.learning_revision += 1
    for row in session.exec(
        select(LearningReport).where(
            LearningReport.session_id == role_session.id,
            LearningReport.kind == "live",
            LearningReport.status == "queued",
        )
    ).all():
        row.status = "superseded"
        row.updated_at = now
    session.flush()
    report = _ensure_report(session, role_session, "final")
    if report is None:  # guarded by has_student
        raise AppError("DATA_INTEGRITY_ERROR", "无法固定学习报告输入", 500)
    return EndSessionResult(
        session_id=role_session.id,
        status="ended",
        report_id=report.id,
        report_status=report.status,
    )


def role_session_mode(session: Session, session_id: str) -> str:
    row = session.get(RoleSession, session_id)
    return row.mode if row else "student"


def ensure_report(
    session: Session, user: User, session_id: str
) -> tuple[ReportQueueResult, int, str | None]:
    task, role_session = _access(session, user, session_id)
    if user.role == "teacher" and task.status != "active":
        raise AppError("TASK_ARCHIVED", "任务已归档", 409)
    kind = "final" if role_session.status == "ended" else "live"
    report = _ensure_report(session, role_session, kind)
    if report is None:
        return ReportQueueResult(report_id=None, status="empty"), 200, None
    status = 200 if report.status != "queued" else 202
    return ReportQueueResult(report_id=report.id, status=report.status), status, report.id


def retry_report(
    session: Session, user: User, report_id: str
) -> tuple[ReportQueueResult, int, str | None]:
    report = session.get(LearningReport, report_id)
    role_session = session.get(RoleSession, report.session_id) if report else None
    if report is None or role_session is None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    task, _ = _access(session, user, role_session.id)
    if user.role == "teacher" and task.status != "active":
        raise AppError("TASK_ARCHIVED", "任务已归档", 409)
    if report.kind == "live" and report.input_revision != role_session.learning_revision:
        raise AppError("REPORT_SUPERSEDED", "该报告已落后，请刷新最新报告", 409)
    if report.status == "failed":
        report.status = "queued"
        report.generation_run_id = None
        report.error_json = None
        report.updated_at = dialogue._now()
        return ReportQueueResult(report_id=report.id, status="queued"), 202, report.id
    return ReportQueueResult(report_id=report.id, status=report.status), 200, None


def _start_generation(
    session: Session, report: LearningReport, settings: Settings
) -> AgentRun | None:
    if report.status != "queued":
        return None
    role_session = session.get(RoleSession, report.session_id)
    if role_session is None:
        return None
    running = session.exec(
        select(AgentRun.id).where(
            AgentRun.session_id == role_session.id,
            AgentRun.kind == "learning_report",
            AgentRun.status == "running",
        )
    ).first()
    if running is not None:
        return None
    now = dialogue._now()
    deadline = (
        (dialogue.datetime.now(dialogue.UTC) + timedelta(seconds=settings.run_timeout_seconds))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    run = AgentRun(
        id=str(uuid4()),
        actor_id=role_session.owner_id,
        task_id=role_session.task_id,
        version_id=role_session.version_id,
        version_revision=role_session.version_revision,
        kind="learning_report",
        status="running",
        session_id=role_session.id,
        source_id=None,
        input_message_id=None,
        output_message_id=None,
        retry_of_run_id=None,
        step_count=0,
        max_steps=settings.run_max_steps,
        deadline_at=deadline,
        cancel_requested_at=None,
        terminal_reason=None,
        execution_config_json=_json(
            {"model": settings.llm_model, "promptVersion": PROMPT_VERSION, "reportId": report.id}
        ),
        result_json=None,
        error_json=None,
        created_at=now,
        finished_at=None,
    )
    session.add(run)
    session.flush()
    report.status = "generating"
    report.generation_run_id = run.id
    report.updated_at = now
    session.add(
        RunEvent(
            id=str(uuid4()),
            run_id=run.id,
            seq=1,
            event_type="run.started",
            payload_json=_json(
                {"runId": run.id, "seq": 1, "kind": "learning_report", "status": "running"}
            ),
            created_at=now,
        )
    )
    return run


def _validate_content(snapshot: dict[str, object], content: ReportContent) -> None:
    student_messages = {
        str(item["messageId"]): str(item["text"])
        for item in snapshot.get("studentMessages", [])
        if isinstance(item, dict) and "messageId" in item and "text" in item
    }
    assistant_messages = {
        str(item["messageId"]): str(item["text"])
        for item in snapshot.get("assistantMessages", [])
        if isinstance(item, dict) and "messageId" in item and "text" in item
    }
    evidence_ids = {
        str(citation["evidenceId"])
        for item in snapshot.get("assistantMessages", [])
        if isinstance(item, dict)
        for citation in item.get("citations", [])
        if isinstance(citation, dict) and citation.get("evidenceId")
    }
    if any(str(item) not in student_messages for item in content.summary.message_ids):
        raise ModelAdapterError("REPORT_INVALID", "报告摘要引用了不属于学生的消息", retryable=True)
    for signal in content.signals:
        message = student_messages.get(str(signal.message_id))
        if message is None or signal.quote not in message:
            raise ModelAdapterError("REPORT_INVALID", "报告摘录不是学生原话", retryable=True)
    for finding in content.findings:
        allowed = assistant_messages if finding.kind == "role_view" else student_messages
        if any(str(item) not in allowed for item in finding.message_ids):
            raise ModelAdapterError("REPORT_INVALID", "报告观点归属不正确", retryable=True)
        if any(str(item) not in evidence_ids for item in finding.evidence_ids):
            raise ModelAdapterError("REPORT_INVALID", "报告引用不属于本会话", retryable=True)


def _metrics(snapshot: dict[str, object], content: ReportContent | None) -> ReportMetrics:
    expression = len(snapshot.get("studentMessages", []))
    events = snapshot.get("events", [])
    source_ids = {
        item.get("sourceId")
        for item in events
        if isinstance(item, dict) and item.get("type") == "source_open" and item.get("sourceId")
    }
    stances = {
        item.get("messageId")
        for item in events
        if isinstance(item, dict) and item.get("type") == "stance" and item.get("messageId")
    }
    tracking = snapshot.get("sourceTracking")
    source_count = len(source_ids) if tracking != "unavailable" else None
    if content is None:
        return ReportMetrics(
            expression_count=expression,
            evidence_seeking_count=None,
            source_view_count=source_count,
            judgment_count=None,
            reflection_count=None,
        )
    evidence = {str(item.message_id) for item in content.signals if "evidence_seeking" in item.tags}
    judgments = {str(item.message_id) for item in content.signals if "judgment" in item.tags}
    reflections = {str(item.message_id) for item in content.signals if "reflection" in item.tags}
    return ReportMetrics(
        expression_count=expression,
        evidence_seeking_count=len(evidence),
        source_view_count=source_count,
        judgment_count=len(judgments) + len(stances),
        reflection_count=len(reflections),
    )


def process_report(
    engine: Any,
    settings: Settings,
    model: StructuredModel,
    runtime: WorkflowRuntime,
    report_id: str,
) -> None:
    run_id: str | None = None
    try:
        # Capacity is acquired before moving the persistent row from queued to
        # generating, so capacity pressure leaves durable work queued for a later trigger.
        with runtime.report_model_slot():
            with Session(engine) as session:
                report = session.get(LearningReport, report_id)
                if report is None:
                    return
                run = _start_generation(session, report, settings)
                if run is None:
                    return
                snapshot = _load(report.input_snapshot_json, {})
                run_id = run.id
                run.step_count = 1
                session.add(
                    RunStep(
                        id=str(uuid4()),
                        run_id=run.id,
                        step_no=1,
                        attempt=1,
                        name="generate_learning_report",
                        status="running",
                        input_summary_json=_json(
                            {"reportId": report.id, "inputRevision": report.input_revision}
                        ),
                        output_summary_json=None,
                        error_json=None,
                        started_at=dialogue._now(),
                        finished_at=None,
                    )
                )
                session.commit()
            content = model.generate(
                system=(
                    "整理学生已经表达的探究过程。只归纳输入中的学生原话；角色观点单列，"
                    "未表达内容放入 missingAspects，不补造结论、观点变化、反思或成绩。"
                ),
                prompt=_json(snapshot),
                schema=ReportContent,
            )
        _validate_content(snapshot, content)
    except Exception as caught:
        if isinstance(caught, AppError) and run_id is None:
            # Report/global model capacity is deliberately non-blocking. The queued
            # row remains the durable retry signal while interactive work proceeds.
            return
        if isinstance(caught, ModelAdapterError):
            error = caught
        elif isinstance(caught, AppError):
            error = ModelAdapterError(caught.code, caught.message, retryable=caught.retryable)
        elif isinstance(caught, ValidationError):
            error = ModelAdapterError("REPORT_INVALID", "报告结构不符合要求", retryable=True)
        else:
            error = ModelAdapterError(
                "REPORT_GENERATION_FAILED", "报告暂未整理完成", retryable=True
            )
        if run_id is not None:
            _finish_report(engine, report_id, run_id, error=error)
        return
    assert run_id is not None
    _finish_report(engine, report_id, run_id, content=content)


def _finish_report(
    engine: Any,
    report_id: str,
    run_id: str,
    *,
    content: ReportContent | None = None,
    error: ModelAdapterError | None = None,
) -> None:
    with Session(engine) as session:
        report = session.get(LearningReport, report_id)
        run = session.get(AgentRun, run_id)
        step = session.exec(select(RunStep).where(RunStep.run_id == run_id)).first()
        if (
            report is None
            or run is None
            or report.status != "generating"
            or report.generation_run_id != run.id
            or run.status != "running"
        ):
            return
        now = dialogue._now()
        if error is None and content is not None:
            report.status = "ready"
            report.content_json = _json(content.model_dump(by_alias=True, mode="json"))
            report.generated_at = now
            report.error_json = None
            run.status = "completed"
            run.result_json = _json({"reportId": report.id})
            run.error_json = None
            if step:
                step.status = "completed"
                step.output_summary_json = _json({"valid": True})
            event_type = "run.completed"
            payload = {"result": {"reportId": report.id}}
        else:
            assert error is not None
            encoded = _json(
                {"code": error.code, "message": error.message, "retryable": error.retryable}
            )
            report.status = "failed"
            report.error_json = encoded
            run.status = "failed"
            run.error_json = encoded
            run.terminal_reason = error.code if error.code == "PROCESS_INTERRUPTED" else None
            if step:
                step.status = "failed"
                step.error_json = encoded
            event_type = "run.failed"
            payload = {"code": error.code, "message": error.message, "retryable": error.retryable}
        report.updated_at = now
        run.finished_at = now
        if step:
            step.finished_at = now
        seq = (
            session.exec(select(func.max(RunEvent.seq)).where(RunEvent.run_id == run.id)).one() or 0
        ) + 1
        session.add(
            RunEvent(
                id=str(uuid4()),
                run_id=run.id,
                seq=seq,
                event_type=event_type,
                payload_json=_json({"runId": run.id, "seq": seq, **payload}),
                created_at=now,
            )
        )
        session.commit()


def report_view(session: Session, row: LearningReport) -> LearningReportView:
    snapshot = _load(row.input_snapshot_json, {})
    content = None
    if row.content_json is not None:
        try:
            content = ReportContent.model_validate(_load(row.content_json, {}))
        except ValidationError:
            content = None
    return LearningReportView(
        id=row.id,
        session_id=row.session_id,
        report_no=row.report_no,
        kind=row.kind,
        status=row.status,
        input_revision=row.input_revision,
        generated_at=row.generated_at,
        content=content,
        metrics=_metrics(snapshot, content),
        source_tracking=str(snapshot.get("sourceTracking", "unavailable")),
    )


def _correction_view(row: ReportCorrection) -> ReportCorrectionView:
    return ReportCorrectionView(
        id=row.id,
        session_id=row.session_id,
        report_id=row.report_id,
        author_id=row.author_id,
        text=row.text,
        created_at=row.created_at,
    )


def report_envelope(session: Session, user: User, session_id: str) -> ReportEnvelope:
    _, role_session = _access(session, user, session_id)
    reports = session.exec(
        select(LearningReport)
        .where(LearningReport.session_id == role_session.id)
        .order_by(LearningReport.input_revision.desc(), LearningReport.report_no.desc())
    ).all()
    desired_kind = "final" if role_session.status == "ended" else "live"
    current = next((row for row in reports if row.kind == desired_kind), None)
    latest_ready = next((row for row in reports if row.status == "ready"), None)
    if current is None:
        freshness = "empty"
    elif current.status in {"queued", "generating"}:
        freshness = "updating"
    elif current.status == "failed":
        freshness = "failed"
    elif current.status == "ready" and current.input_revision == role_session.learning_revision:
        freshness = "current"
    else:
        freshness = "updating"
    corrections = session.exec(
        select(ReportCorrection)
        .where(ReportCorrection.session_id == role_session.id)
        .order_by(ReportCorrection.created_at, ReportCorrection.id)
        .limit(51)
    ).all()
    more = len(corrections) > 50
    corrections = corrections[:50]
    return ReportEnvelope(
        session_id=role_session.id,
        session_status=role_session.status,
        current_learning_revision=role_session.learning_revision,
        current_report=report_view(session, current) if current else None,
        latest_ready_report=report_view(session, latest_ready) if latest_ready else None,
        freshness=freshness,
        corrections=[_correction_view(row) for row in corrections],
        next_correction_cursor=corrections[-1].id if more else None,
        legacy_submission=legacy_submission(session, user, role_session.id),
    )


def add_correction(
    session: Session, user: User, session_id: str, report_id: str, text: str
) -> ReportCorrectionView:
    _, role_session = _access(session, user, session_id, student_write=True)
    report = session.get(LearningReport, report_id)
    if report is None or report.session_id != role_session.id or report.status != "ready":
        raise AppError("NOT_FOUND", "可补充的报告不存在", 404)
    row = ReportCorrection(
        id=str(uuid4()),
        session_id=role_session.id,
        report_id=report.id,
        author_id=user.id,
        text=text.strip(),
        created_at=dialogue._now(),
    )
    session.add(row)
    session.flush()
    return _correction_view(row)


def list_corrections(
    session: Session, user: User, session_id: str, *, limit: int, cursor: str | None
) -> CorrectionPage:
    _, role_session = _access(session, user, session_id)
    statement = select(ReportCorrection).where(ReportCorrection.session_id == role_session.id)
    if cursor:
        statement = statement.where(ReportCorrection.id > cursor)
    rows = session.exec(statement.order_by(ReportCorrection.id).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    return CorrectionPage(
        items=[_correction_view(row) for row in rows],
        next_cursor=rows[-1].id if more else None,
    )


def resume_pending_reports(
    engine: Any,
    settings: Settings,
    runtime: WorkflowRuntime,
    model_factory,
) -> None:
    with Session(engine) as session:
        pending = session.exec(
            select(LearningReport.id).where(LearningReport.status == "queued")
        ).first()
    if pending is None:
        return
    try:
        model = model_factory(settings)
    except ModelAdapterError as error:
        fail_queued_reports(engine, settings, error)
        return
    process_pending_reports(engine, settings, model, runtime)


def fail_queued_reports(engine: Any, settings: Settings, error: ModelAdapterError) -> int:
    with Session(engine) as session:
        ids = session.exec(select(LearningReport.id).where(LearningReport.status == "queued")).all()
        now = dialogue._now()
        for report_id in ids:
            report = session.get(LearningReport, report_id)
            role_session = session.get(RoleSession, report.session_id) if report else None
            if report is None or role_session is None:
                continue
            run = _start_generation(session, report, settings)
            if run is not None:
                run.error_json = _json(
                    {"code": error.code, "message": error.message, "retryable": error.retryable}
                )
                run.status = "failed"
                run.finished_at = now
                report.status = "failed"
                report.error_json = run.error_json
                report.updated_at = now
        session.commit()
    return len(ids)


def process_pending_reports(
    engine: Any,
    settings: Settings,
    model: StructuredModel,
    runtime: WorkflowRuntime,
    *,
    session_id: str | None = None,
) -> None:
    """Drain eligible persisted reports; final reports take priority over live reports."""
    while True:
        with Session(engine) as session:
            statement = select(LearningReport).where(LearningReport.status == "queued")
            if session_id is not None:
                statement = statement.where(LearningReport.session_id == session_id)
            rows = session.exec(
                statement.order_by(LearningReport.created_at, LearningReport.id)
            ).all()
            if not rows:
                return
            rows.sort(key=lambda row: (row.kind != "final", row.created_at, row.id))
            report_id = rows[0].id
        process_report(engine, settings, model, runtime, report_id)
        with Session(engine) as session:
            current = session.get(LearningReport, report_id)
            if current is not None and current.status == "queued":
                # Another worker owns the session-level report slot; keep the row persisted
                # for the next explicit trigger/startup recovery instead of spinning.
                return


def fail_interrupted_report_runs(engine: Any) -> int:
    with Session(engine) as session:
        ids = session.exec(
            select(AgentRun.id).where(
                AgentRun.kind == "learning_report", AgentRun.status == "running"
            )
        ).all()
    for run_id in ids:
        with Session(engine) as session:
            report = session.exec(
                select(LearningReport).where(LearningReport.generation_run_id == run_id)
            ).first()
            report_id = report.id if report else ""
        if report_id:
            _finish_report(
                engine,
                report_id,
                run_id,
                error=ModelAdapterError(
                    "PROCESS_INTERRUPTED", "服务重启中断了报告整理", retryable=True
                ),
            )
    return len(ids)
