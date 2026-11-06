"""P4 single-role sessions, evidence-grounded chat, and memory summaries."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from rank_bm25 import BM25Okapi
from sqlalchemy import func, text
from sqlmodel import Session, select

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models import (
    AgentRun,
    Citation,
    Evidence,
    Message,
    ReviewRecord,
    RoleCard,
    RoleSession,
    RunEvent,
    RunStep,
    Source,
    Task,
    TaskMember,
    TaskVersion,
    User,
    VersionSource,
)
from app.integrations.model import DialogueModel, ModelAdapterError
from app.schemas.contracts import AnswerBlock, TaskBrief
from app.schemas.contracts import RoleCard as RoleCardContract
from app.schemas.model_outputs import (
    AnswerCheckOutput,
    ConversationSummaryOutput,
    DialogueLine,
    FollowUpOutput,
)
from app.schemas.session_dtos import (
    CitationView,
    MessageMeta,
    MessagePage,
    MessageView,
    PublicRole,
    RoleSessionView,
    SessionListItem,
    SessionPage,
    StartedMessageRun,
    SummaryResult,
)
from app.services import idempotency, materials, p3
from app.workflows.runtime import WorkflowRuntime

PROMPT_VERSION = "p4-dialogue-v3"
RECENT_ROUNDS = 6
EVIDENCE_TOP_K = 6
MAX_BLOCKS = 6


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _future(seconds: int) -> str:
    return (
        (datetime.now(UTC) + timedelta(seconds=seconds))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _event(session: Session, run: AgentRun, event_type: str, payload: dict[str, object]) -> int:
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
            created_at=_now(),
        )
    )
    return seq


def _task_and_session(session: Session, user: User, session_id: str, *, write: bool = False):
    role_session = session.get(RoleSession, session_id)
    if role_session is None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    task = session.get(Task, role_session.task_id)
    if task is None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    owner = role_session.owner_id == user.id
    teacher = user.role == "teacher" and task.owner_id == user.id
    if not owner and not teacher:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    if role_session.mode == "student":
        member = session.get(TaskMember, (task.id, user.id)) if owner else None
        if owner and (task.status != "active" or member is None):
            raise AppError("NOT_FOUND", "资源不存在", 404)
    elif teacher and task.status == "archived" and write:
        raise AppError("TASK_ARCHIVED", "任务已归档", 409)
    if write and not owner:
        raise AppError("FORBIDDEN", "教师不能代替会话所有者发言", 403)
    return task, role_session


def _session_snapshot(session: Session, version: TaskVersion) -> dict[str, object]:
    brief = TaskBrief.model_validate(_load(version.brief_json, {})).model_dump(
        by_alias=True, mode="json"
    )
    role_row = session.exec(select(RoleCard).where(RoleCard.version_id == version.id)).first()
    if role_row is None:
        raise AppError("VALIDATION_ERROR", "请先完善对话角色", 422)
    role = RoleCardContract.model_validate(
        {"roleId": role_row.id, **_load(role_row.card_json, {})}
    ).model_dump(by_alias=True, mode="json")
    linked_ready = set(
        session.exec(
            select(Source.id)
            .join(VersionSource, VersionSource.source_id == Source.id)
            .where(VersionSource.version_id == version.id, Source.status == "ready")
        ).all()
    )
    role_sources = set(map(str, role.get("sourceIds", [])))
    if not role_sources:
        # Older generated cards could omit every source even though the teacher had
        # linked ready materials and there is no separate per-role source selector.
        role_sources = linked_ready
        role["sourceIds"] = sorted(role_sources)
    if not role_sources.issubset(linked_ready):
        raise AppError("SOURCE_NOT_READY", "角色引用的资料尚未准备完成", 422)
    return {
        "brief": brief,
        "roleCard": role,
        "questionPlan": _load(version.question_plan_json, []),
        "allowedSourceIds": sorted(role_sources),
        "contentHash": version.content_hash or p3.content_hash(session, version),
    }


def _public_role(snapshot: dict[str, object]) -> PublicRole:
    role = snapshot.get("roleCard", {})
    if not isinstance(role, dict):
        raise AppError("DATA_INTEGRITY_ERROR", "会话角色快照无效", 500)
    return PublicRole.model_validate(
        {
            "roleId": role.get("roleId"),
            "name": role.get("name"),
            "roleType": role.get("roleType"),
            "identityDescription": role.get("identityDescription"),
            "timeAnchor": role.get("timeAnchor"),
            "openingMessage": role.get("openingMessage"),
            "recommendedQuestions": role.get("recommendedQuestions", []),
        }
    )


def session_view(row: RoleSession) -> RoleSessionView:
    snapshot = _load(row.snapshot_json, {})
    tracking = "unavailable"
    if row.event_tracking_started_at is not None:
        tracking = "complete" if row.event_tracking_started_at == row.created_at else "partial"
    summary = _load(row.summary_json, {})
    return RoleSessionView(
        id=row.id,
        task_id=row.task_id,
        version_id=row.version_id,
        version_revision=row.version_revision,
        owner_id=row.owner_id,
        mode=row.mode,
        status=row.status,
        completed_turns=row.completed_turns,
        learning_revision=row.learning_revision,
        source_tracking=tracking,
        public_role=_public_role(snapshot),
        summary=summary if isinstance(summary, dict) else {},
        created_at=row.created_at,
        ended_at=row.ended_at,
    )


def create_preview_session(
    session: Session, user: User, version_id: str, expected_revision: int
) -> RoleSessionView:
    task, version = p3._owner_draft(session, user, version_id)
    p3._check_revision(version, expected_revision)
    snapshot = _session_snapshot(session, version)
    now = _now()
    row = RoleSession(
        id=str(uuid4()),
        task_id=task.id,
        version_id=version.id,
        version_revision=version.revision,
        owner_id=user.id,
        mode="preview",
        status="active",
        snapshot_json=_json(snapshot),
        summary_json="{}",
        summary_through_seq=0,
        completed_turns=0,
        learning_revision=0,
        event_tracking_started_at=None,
        ended_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    return session_view(row)


def create_student_session(
    session: Session, user: User, task_id: str
) -> tuple[RoleSessionView, int]:
    task = session.get(Task, task_id)
    if (
        task is None
        or user.role != "student"
        or task.status != "active"
        or session.get(TaskMember, (task_id, user.id)) is None
    ):
        raise AppError("NOT_FOUND", "资源不存在", 404)
    if task.current_published_version_id is None:
        raise AppError("VERSION_NOT_PUBLISHED", "任务尚未发布", 409)
    existing = session.exec(
        select(RoleSession).where(
            RoleSession.owner_id == user.id,
            RoleSession.version_id == task.current_published_version_id,
            RoleSession.mode == "student",
        )
    ).first()
    if existing is not None:
        return session_view(existing), 200
    version = session.get(TaskVersion, task.current_published_version_id)
    if version is None or version.status != "published":
        raise AppError("VERSION_NOT_PUBLISHED", "任务尚未发布", 409)
    snapshot = _session_snapshot(session, version)
    now = _now()
    row = RoleSession(
        id=str(uuid4()),
        task_id=task.id,
        version_id=version.id,
        version_revision=version.revision,
        owner_id=user.id,
        mode="student",
        status="active",
        snapshot_json=_json(snapshot),
        summary_json="{}",
        summary_through_seq=0,
        completed_turns=0,
        learning_revision=0,
        event_tracking_started_at=now,
        ended_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    return session_view(row), 201


def get_session(session: Session, user: User, session_id: str) -> RoleSessionView:
    _, row = _task_and_session(session, user, session_id)
    return session_view(row)


def _citation_views(session: Session, message_ids: list[str]) -> dict[str, list[CitationView]]:
    result: dict[str, list[CitationView]] = {message_id: [] for message_id in message_ids}
    if not message_ids:
        return result
    rows = session.exec(
        select(Citation, Evidence, Source)
        .join(Evidence, Evidence.id == Citation.evidence_id)
        .join(Source, Source.id == Evidence.source_id)
        .where(Citation.message_id.in_(message_ids))
        .order_by(Citation.message_id, Citation.block_index, Citation.id)
    ).all()
    for citation, evidence, source in rows:
        result[citation.message_id].append(
            CitationView(
                id=citation.id,
                message_id=citation.message_id,
                block_index=citation.block_index,
                evidence_id=evidence.id,
                source_id=source.id,
                file_name=source.file_name,
                page_no=evidence.page_no,
                start_line=evidence.start_line,
                end_line=evidence.end_line,
                paragraph_no=evidence.paragraph_no,
                quote=citation.quote,
            )
        )
    return result


def _message_views(session: Session, rows: list[Message]) -> list[MessageView]:
    citations = _citation_views(session, [row.id for row in rows])
    result: list[MessageView] = []
    for row in rows:
        blocks = _load(row.blocks_json, [])
        meta = _load(row.meta_json, {})
        result.append(
            MessageView(
                id=row.id,
                session_id=row.session_id,
                seq=row.seq,
                speaker=row.speaker,
                status=row.status,
                text=row.text,
                blocks=[AnswerBlock.model_validate(item) for item in blocks],
                citations=citations[row.id],
                run_id=row.run_id,
                supersedes_message_id=row.supersedes_message_id,
                meta=MessageMeta.model_validate(meta if isinstance(meta, dict) else {}),
                created_at=row.created_at,
            )
        )
    return result


def list_messages(
    session: Session, user: User, session_id: str, *, after_seq: int, limit: int
) -> MessagePage:
    _, role_session = _task_and_session(session, user, session_id)
    rows = session.exec(
        select(Message)
        .where(Message.session_id == role_session.id, Message.seq > after_seq)
        .order_by(Message.seq)
        .limit(limit + 1)
    ).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return MessagePage(
        items=_message_views(session, rows),
        next_after_seq=rows[-1].seq if rows else after_seq,
        has_more=has_more,
    )


def list_task_sessions(
    session: Session, user: User, task_id: str, *, limit: int, cursor: str | None
) -> SessionPage:
    task = session.get(Task, task_id)
    if task is None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    if user.role == "teacher" and task.owner_id == user.id:
        mode = "preview"
    elif user.role == "student" and session.get(TaskMember, (task.id, user.id)) is not None:
        mode = "student"
    else:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    statement = (
        select(RoleSession, TaskVersion)
        .join(TaskVersion, TaskVersion.id == RoleSession.version_id)
        .where(
            RoleSession.task_id == task.id,
            RoleSession.owner_id == user.id,
            RoleSession.mode == mode,
        )
    )
    if cursor:
        statement = statement.where(RoleSession.id < cursor)
    rows = session.exec(statement.order_by(RoleSession.id.desc()).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return SessionPage(
        items=[
            SessionListItem(
                id=row.id,
                version_id=row.version_id,
                version_no=version.version_no,
                status=row.status,
                completed_turns=row.completed_turns,
                created_at=row.created_at,
            )
            for row, version in rows
        ],
        next_cursor=rows[-1][0].id if has_more and rows else None,
    )


def _limits(snapshot: dict[str, object]) -> tuple[int, str | None]:
    brief = snapshot.get("brief", {})
    restrictions = brief.get("restrictions", {}) if isinstance(brief, dict) else {}
    if not isinstance(restrictions, dict):
        return 20, None
    return int(restrictions.get("maxTurns", 20)), restrictions.get("deadlineAt")


def _ensure_can_run(role_session: RoleSession) -> None:
    if role_session.status != "active":
        raise AppError("SESSION_ENDED", "探究已经结束", 409)
    snapshot = _load(role_session.snapshot_json, {})
    max_turns, deadline = _limits(snapshot)
    if role_session.completed_turns >= max_turns:
        raise AppError("MAX_TURNS_REACHED", "已达到最大对话轮次", 409)
    if isinstance(deadline, str) and deadline and deadline <= _now():
        raise AppError("DEADLINE_REACHED", "探究截止时间已到", 409)


def _new_chat_run(
    session: Session,
    user: User,
    role_session: RoleSession,
    input_message: Message,
    output_message: Message,
    settings: Settings,
    *,
    retry_of: str | None = None,
) -> AgentRun:
    now = _now()
    run_id = output_message.run_id or str(uuid4())
    run = AgentRun(
        id=run_id,
        actor_id=user.id,
        task_id=role_session.task_id,
        version_id=role_session.version_id,
        version_revision=role_session.version_revision,
        kind="chat",
        status="running",
        session_id=role_session.id,
        source_id=None,
        input_message_id=input_message.id,
        output_message_id=output_message.id,
        retry_of_run_id=retry_of,
        step_count=0,
        max_steps=settings.run_max_steps,
        deadline_at=_future(settings.run_timeout_seconds),
        cancel_requested_at=None,
        terminal_reason=None,
        execution_config_json=_json({"model": settings.llm_model, "promptVersion": PROMPT_VERSION}),
        result_json=None,
        error_json=None,
        created_at=now,
        finished_at=None,
    )
    output_message.run_id = run.id
    # SQLite's immediate circular FKs require temporarily deferring checks until
    # this short transaction commits both linked rows.
    session.execute(text("PRAGMA defer_foreign_keys=ON"))
    session.add(run)
    session.add(output_message)
    session.flush()
    _event(session, run, "run.started", {"kind": "chat", "status": "running"})
    return run


def start_message(
    session: Session,
    user: User,
    session_id: str,
    content: str,
    settings: Settings,
    *,
    path: str,
    idempotency_key: str | None,
) -> tuple[StartedMessageRun, int, str]:
    _, role_session = _task_and_session(session, user, session_id, write=True)
    _ensure_can_run(role_session)
    text = content.strip()
    if not text:
        raise AppError("VALIDATION_ERROR", "消息不能为空", 422)
    reservation = idempotency.begin(
        session,
        user_id=user.id,
        method="POST",
        path=path,
        key=idempotency_key,
        digest=idempotency.request_hash("POST", path, {"content": text}),
    )
    if reservation.replay is not None:
        data = StartedMessageRun.model_validate(reservation.replay.body)
        return data, reservation.replay.status, data.run_id
    active = session.exec(
        select(AgentRun).where(
            AgentRun.session_id == role_session.id,
            AgentRun.status == "running",
            AgentRun.kind.in_(("chat", "summary")),
        )
    ).first()
    if active is not None:
        raise AppError("RUN_ALREADY_ACTIVE", "当前回答尚未结束", 409)
    max_seq = (
        session.exec(
            select(func.max(Message.seq)).where(Message.session_id == role_session.id)
        ).one()
        or 0
    )
    now = _now()
    user_message = Message(
        id=str(uuid4()),
        session_id=role_session.id,
        seq=max_seq + 1,
        speaker="user",
        status="complete",
        text=text,
        blocks_json="[]",
        meta_json="{}",
        run_id=None,
        supersedes_message_id=None,
        created_at=now,
        updated_at=now,
    )
    assistant = Message(
        id=str(uuid4()),
        session_id=role_session.id,
        seq=max_seq + 2,
        speaker="assistant",
        status="pending",
        text="",
        blocks_json="[]",
        meta_json="{}",
        run_id=None,
        supersedes_message_id=None,
        created_at=now,
        updated_at=now,
    )
    session.add(user_message)
    session.flush()
    # These rows form a deliberate circular FK. SQLite supports a deferred check;
    # issue both inserts in one flush so neither incomplete row is visible.
    assistant.run_id = str(uuid4())
    run = _new_chat_run(session, user, role_session, user_message, assistant, settings)
    if role_session.mode == "student":
        role_session.learning_revision += 1
    role_session.updated_at = now
    data = StartedMessageRun(
        user_message_id=user_message.id, assistant_message_id=assistant.id, run_id=run.id
    )
    idempotency.complete(
        session, reservation, status=202, body=data.model_dump(by_alias=True), resource_id=run.id
    )
    session.commit()
    return data, 202, run.id


def _step(session: Session, run: AgentRun, name: str, summary: dict[str, object]) -> RunStep:
    if run.step_count >= run.max_steps or run.deadline_at <= _now():
        code = "STEP_LIMIT_REACHED" if run.step_count >= run.max_steps else "RUN_TIMEOUT"
        raise ModelAdapterError(code, "运行已达到限制", retryable=False)
    run.step_count += 1
    row = RunStep(
        id=str(uuid4()),
        run_id=run.id,
        step_no=run.step_count,
        attempt=1,
        name=name,
        status="running",
        input_summary_json=_json(summary),
        output_summary_json=None,
        error_json=None,
        started_at=_now(),
        finished_at=None,
    )
    session.add(row)
    session.commit()
    return row


def _complete_step(session: Session, step: RunStep, output: dict[str, object]) -> None:
    step.status = "completed"
    step.output_summary_json = _json(output)
    step.finished_at = _now()


def _fail_step(session: Session, step: RunStep, error: ModelAdapterError) -> None:
    step.status = "failed"
    step.error_json = _json(
        {"code": error.code, "message": error.message, "retryable": error.retryable}
    )
    step.finished_at = _now()


def _candidate_evidence(session: Session, role_session: RoleSession, query: str):
    snapshot = _load(role_session.snapshot_json, {})
    allowed = snapshot.get("allowedSourceIds", [])
    if not isinstance(allowed, list):
        allowed = []
    if not allowed and role_session.mode == "student":
        # Published versions are immutable. This compatibility path repairs older
        # student-session snapshots created while generated role cards could
        # accidentally omit every linked source.
        allowed = list(
            session.exec(
                select(Source.id)
                .join(VersionSource, VersionSource.source_id == Source.id)
                .where(
                    VersionSource.version_id == role_session.version_id,
                    Source.status == "ready",
                )
                .order_by(Source.id)
            ).all()
        )
    if not allowed:
        return []
    rows = session.exec(
        select(Evidence, Source)
        .join(Source, Source.id == Evidence.source_id)
        .where(Evidence.source_id.in_(allowed), Source.status == "ready")
        .order_by(Evidence.source_id, Evidence.ordinal)
    ).all()
    if not rows:
        return []
    role = snapshot.get("roleCard", {})
    brief = snapshot.get("brief", {})
    context_terms = [query]
    if isinstance(role, dict):
        context_terms.extend(
            str(role.get(key, ""))
            for key in ("name", "identityDescription", "historicalPeriod", "position")
        )
    if isinstance(brief, dict):
        context_terms.extend(str(brief.get(key, "")) for key in ("topicName", "coreQuestion"))
    retrieval_query = " ".join(term for term in context_terms if term)
    corpus = [materials._tokens(evidence.text) for evidence, _ in rows]
    query_tokens = materials._tokens(retrieval_query)
    if not query_tokens:
        return []
    scores = BM25Okapi(corpus).get_scores(query_tokens)
    query_set = set(query_tokens)
    ranked = sorted(
        enumerate(scores),
        key=lambda item: (
            -sum(1 for token in corpus[item[0]] if token in query_set),
            -float(item[1]),
            item[0],
        ),
    )
    return [
        rows[index]
        for index, score in ranked[:EVIDENCE_TOP_K]
        if float(score) > 0 or query_set.intersection(corpus[index])
    ]


def _recent_messages(session: Session, role_session: RoleSession) -> list[dict[str, object]]:
    rows = session.exec(
        select(Message)
        .where(
            Message.session_id == role_session.id,
            ((Message.speaker == "user") | (Message.status == "complete")),
        )
        .order_by(Message.seq.desc())
        .limit(RECENT_ROUNDS * 2 + 1)
    ).all()
    return [{"speaker": row.speaker, "text": row.text, "seq": row.seq} for row in reversed(rows)]


def _generation_prompt(
    role_session: RoleSession,
    question: str,
    evidence_rows,
    recent_messages: list[dict[str, object]],
) -> tuple[str, str]:
    snapshot = _load(role_session.snapshot_json, {})
    evidence = [
        {
            "evidenceId": item.id,
            "sourceId": item.source_id,
            "text": item.text,
            "pageNo": item.page_no,
            "startLine": item.start_line,
            "endLine": item.end_line,
        }
        for item, _ in evidence_rows
    ]
    system = (
        "你在单一角色探究学习中扮演给定角色，要像这个人物一样与学生展开有内容的对话，"
        "而不是充当只会拒答的资料审查器。先直接回答学生实际提出的问题，再说明证据与边界。"
        "固定遵守角色身份、时间、已知未知范围，不编造私人动机，不替学生下结论。"
        "优先使用给定 evidence 回答可核对的历史问题，并引用相应 evidenceId；"
        "角色卡中的身份、时间、处境和 teacher 来源 knownFacts 可作为角色设定自然表达，"
        "但不得伪称为资料原文。可以基于多条资料作谨慎推断；只在推断容易被误认成事实时，"
        "才用一句自然的限定语说明，不要机械重复‘这是推断’。"
        "只有问题确实涉及资料未记录的私人感受、秘密动机、未来信息，或现有内容无法支持时，"
        "才使用 unknown；即使如此，也先回答能够确认的相关部分。若已完整回答可支持的内容，"
        "不要在结尾追加‘未曾明说’‘材料未载’‘不凭空补说’‘不替你补成定论’等防御性免责声明，"
        "也不要主动枚举自己无法确认的细节。仅当学生实际追问的核心就是未知内容时，才简洁说明边界。"
        "不要因为证据片段为空就反复输出同义的拒答，也不要把每个问题都改写成待查问题。"
        "只输出 JSON Lines；每行一个对象，字段仅为 type、text、evidenceIds。"
        "type 只能是 fact/opinion/inference/unknown。资料事实必须引用给定 evidenceId；"
        "最多四行，各行承担不同作用，不要 Markdown。"
    )
    prompt = _json(
        {
            "snapshot": snapshot,
            "summary": _load(role_session.summary_json, {}),
            "recentMessages": recent_messages,
            "question": question,
            "evidence": evidence,
        }
    )
    return system, prompt


def _check_prompt(snapshot, question, block, evidence_rows, previous_blocks) -> str:
    return _json(
        {
            "roleCard": snapshot.get("roleCard"),
            "brief": snapshot.get("brief"),
            "question": question,
            "candidateBlock": block,
            "previousAcceptedBlocks": previous_blocks,
            "evidence": [{"evidenceId": item.id, "text": item.text} for item, _ in evidence_rows],
            "requirements": [
                "候选块只是整轮回答的一个分段，不因单块未覆盖整道问题而判失败",
                "核验原文是否支持资料事实；角色设定与 teacher 来源 knownFacts 可作为角色表达，"
                "但不能伪称资料原文",
                "优先保留能够回答问题且证据充分的内容，不要把可回答内容过度修复成拒答",
                "仅在学生实际追问私人感受、秘密动机、未来信息或确实无依据的内容时接受 unknown，"
                "且避免多个同义拒答块",
                "完整回答可支持内容后，不追加材料边界或不编造声明，也不主动枚举未知细节",
                "核验身份、时间与认知边界",
                "不编造私人动机或亲历",
                "不与已接受块矛盾",
                "不代写学生结论",
            ],
        }
    )


def _deterministic_block(block: AnswerBlock, evidence_by_id: dict[str, Evidence]) -> None:
    if block.type == "fact" and not block.evidence_ids:
        raise ModelAdapterError("ANSWER_REJECTED", "事实回答缺少资料依据", retryable=False)
    if any(str(evidence_id) not in evidence_by_id for evidence_id in block.evidence_ids):
        raise ModelAdapterError("ANSWER_REJECTED", "回答引用超出本轮候选资料", retryable=False)


def _persist_block(
    engine,
    run_id: str,
    block: AnswerBlock,
    evidence_by_id: dict[str, Evidence],
    issues: list[dict[str, object]],
) -> bool:
    with Session(engine) as session:
        run = session.get(AgentRun, run_id)
        if run is None or run.status != "running" or run.cancel_requested_at is not None:
            return False
        message = session.get(Message, run.output_message_id)
        if message is None:
            return False
        blocks = _load(message.blocks_json, [])
        block_data = block.model_dump(by_alias=True, mode="json")
        blocks.append(block_data)
        message.blocks_json = _json(blocks)
        message.text = "\n\n".join(str(item["text"]) for item in blocks)
        message.status = "partial"
        message.updated_at = _now()
        citation_views: list[dict[str, object]] = []
        for evidence_id in map(str, block.evidence_ids):
            evidence = session.get(Evidence, evidence_id)
            source = session.get(Source, evidence.source_id) if evidence is not None else None
            if evidence is None or source is None:
                return False
            citation = Citation(
                id=str(uuid4()),
                message_id=message.id,
                block_index=block.block_index,
                evidence_id=evidence.id,
                quote=evidence.text,
                created_at=_now(),
            )
            session.add(citation)
            citation_views.append(
                CitationView(
                    id=citation.id,
                    message_id=message.id,
                    block_index=block.block_index,
                    evidence_id=evidence.id,
                    source_id=source.id,
                    file_name=source.file_name,
                    page_no=evidence.page_no,
                    start_line=evidence.start_line,
                    end_line=evidence.end_line,
                    paragraph_no=evidence.paragraph_no,
                    quote=evidence.text,
                ).model_dump(by_alias=True)
            )
        session.add(
            ReviewRecord(
                id=str(uuid4()),
                task_id=run.task_id,
                version_id=run.version_id,
                version_revision=run.version_revision,
                kind="answer_check",
                session_id=run.session_id,
                run_id=run.id,
                message_id=message.id,
                block_index=block.block_index,
                actor_id=None,
                passed=1,
                result_json=_json({"evidenceIds": list(map(str, block.evidence_ids))}),
                issues_json=_json(issues),
                created_at=_now(),
            )
        )
        _event(
            session,
            run,
            "answer.block",
            {"messageId": message.id, "block": block_data, "citations": citation_views},
        )
        session.commit()
        return True


def _terminal(
    engine,
    run_id: str,
    *,
    status: str,
    error: ModelAdapterError | None = None,
    reason: str | None = None,
    meta: dict[str, object] | None = None,
) -> None:
    with Session(engine) as session:
        run = session.get(AgentRun, run_id)
        if run is None or run.status != "running":
            return
        message = session.get(Message, run.output_message_id)
        role_session = session.get(RoleSession, run.session_id)
        if message is None or role_session is None:
            return
        blocks = _load(message.blocks_json, [])
        now = _now()
        if status == "completed" and run.cancel_requested_at is None:
            message.status = "complete"
            snapshot = _load(role_session.snapshot_json, {})
            role = snapshot.get("roleCard", {}) if isinstance(snapshot, dict) else {}
            message.meta_json = _json(
                {
                    "roleId": role.get("roleId"),
                    "roleType": role.get("roleType"),
                    "timeAnchor": role.get("timeAnchor"),
                    "followUpQuestions": (meta or {}).get("followUpQuestions", []),
                    "phase": "answer",
                    "memorySummary": (meta or {}).get("memorySummary"),
                }
            )
            role_session.completed_turns += 1
            if role_session.mode == "student":
                role_session.learning_revision += 1
            run.result_json = _json({"messageId": message.id})
            run.finished_at = now
            run.status = "completed"
            _event(
                session,
                run,
                "run.completed",
                {"messageId": message.id, "completedTurns": role_session.completed_turns},
            )
        elif run.cancel_requested_at is not None or status == "cancelled":
            message.status = "partial" if blocks else "discarded"
            run.terminal_reason = "USER_CANCELLED"
            run.finished_at = now
            run.status = "cancelled"
            _event(
                session,
                run,
                "run.cancelled",
                {
                    "reason": reason or "用户已停止",
                    "partialMessageId": message.id if blocks else None,
                },
            )
        else:
            message.status = "partial" if blocks else "discarded"
            assert error is not None
            run.error_json = _json(
                {"code": error.code, "message": error.message, "retryable": error.retryable}
            )
            run.terminal_reason = (
                error.code
                if error.code
                in {"ANSWER_REJECTED", "STEP_LIMIT_REACHED", "RUN_TIMEOUT", "PROCESS_INTERRUPTED"}
                else None
            )
            run.finished_at = now
            run.status = "failed"
            _event(
                session,
                run,
                "run.failed",
                {
                    "code": error.code,
                    "message": error.message,
                    "retryable": error.retryable,
                    "partialMessageId": message.id if blocks else None,
                },
            )
        message.updated_at = now
        role_session.updated_at = now
        session.commit()
        if role_session.mode == "student":
            from app.services import learning

            with Session(engine) as report_session:
                fresh_role_session = report_session.get(RoleSession, role_session.id)
                if fresh_role_session is not None:
                    learning._queue_latest_live(report_session, fresh_role_session)
                    report_session.commit()


def _generate_structured_with_retries(
    engine: Any,
    run_id: str,
    model: DialogueModel,
    runtime: WorkflowRuntime,
    *,
    name: str,
    system: str,
    prompt: str,
    schema,
    summary: dict[str, object],
):
    last_error: ModelAdapterError | None = None
    for attempt in range(1, 4):
        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            if run is None or run.status != "running" or run.cancel_requested_at is not None:
                raise ModelAdapterError("USER_CANCELLED", "用户已停止", retryable=False)
            step = _step(session, run, name, {**summary, "attempt": attempt})
            step_id = step.id
        try:
            with runtime.model_slot():
                output = model.generate(system=system, prompt=prompt, schema=schema)
        except ModelAdapterError as error:
            with Session(engine) as session:
                step = session.get(RunStep, step_id)
                if step is not None:
                    _fail_step(session, step, error)
                    session.commit()
            last_error = error
            if not error.retryable:
                raise
            continue
        with Session(engine) as session:
            step = session.get(RunStep, step_id)
            if step is not None:
                _complete_step(session, step, {"valid": True})
                session.commit()
        return output
    assert last_error is not None
    raise last_error


def _next_model_chunk(chunks, runtime: WorkflowRuntime) -> tuple[str | None, bool]:
    with runtime.model_slot():
        try:
            return next(chunks), False
        except StopIteration:
            return None, True


def _review_and_persist_line(
    engine: Any,
    run_id: str,
    model: DialogueModel,
    runtime: WorkflowRuntime,
    *,
    line: str,
    index: int,
    snapshot: dict[str, object],
    question: str,
    evidence_rows,
    evidence_by_id: dict[str, Evidence],
    accepted: list[dict[str, object]],
) -> bool:
    try:
        candidate = DialogueLine.model_validate_json(line)
        block = AnswerBlock.model_validate(
            {"blockIndex": index, **candidate.model_dump(by_alias=True, mode="json")}
        )
        _deterministic_block(block, evidence_by_id)
        passed = False
        issues: list[dict[str, object]] = []
        for attempt in range(3):
            check = _generate_structured_with_retries(
                engine,
                run_id,
                model,
                runtime,
                name="check_role_consistency",
                system=(
                    "你是回答核验器。候选块只是整轮回答的一个分段，不要求单块覆盖完整问题。"
                    "判断本块是否有原文支持并符合角色身份、时间、认知和教学边界。"
                    "核验的目标是在不编造的前提下保留有内容、能回应学生的角色回答，不是把回答"
                    "一律改成无法确认；只有私人感受、秘密动机、未来信息或确实缺乏依据时才应"
                    "使用 unknown。不通过时尽量给出修复后的完整 AnswerBlock。"
                ),
                prompt=_check_prompt(
                    snapshot,
                    question,
                    block.model_dump(by_alias=True, mode="json"),
                    evidence_rows,
                    accepted,
                ),
                schema=AnswerCheckOutput,
                summary={"blockIndex": index, "repairAttempt": attempt + 1},
            )
            issues = [item.model_dump(by_alias=True, mode="json") for item in check.issues]
            if check.passed:
                passed = True
                break
            if check.repaired_block is not None:
                repaired = check.repaired_block.model_copy(update={"block_index": index})
                _deterministic_block(repaired, evidence_by_id)
                block = repaired
        if not passed:
            raise ModelAdapterError("ANSWER_REJECTED", "回答未通过角色与依据核验", retryable=False)
        if not _persist_block(engine, run_id, block, evidence_by_id, issues):
            return False
        accepted.append(block.model_dump(by_alias=True, mode="json"))
        return True
    except (ValidationError, json.JSONDecodeError) as exc:
        raise ModelAdapterError("ANSWER_REJECTED", "回答块格式无效", retryable=True) from exc


def process_chat(
    engine: Any, settings: Settings, model: DialogueModel, runtime: WorkflowRuntime, run_id: str
) -> None:
    cancel = runtime.register(run_id)
    try:
        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            if run is None or run.status != "running":
                return
            role_session = session.get(RoleSession, run.session_id)
            question_message = session.get(Message, run.input_message_id)
            if role_session is None or question_message is None:
                return
            recent_messages = _recent_messages(session, role_session)
            evidence_rows = _candidate_evidence(session, role_session, question_message.text)
            evidence_by_id = {item.id: item for item, _ in evidence_rows}
            generation_step = _step(
                session, run, "generate_answer_jsonl", {"evidenceCount": len(evidence_rows)}
            )
            step_id = generation_step.id
            system, prompt = _generation_prompt(
                role_session, question_message.text, evidence_rows, recent_messages
            )
            snapshot = _load(role_session.snapshot_json, {})
            question = question_message.text
        buffer = ""
        lines: list[str] = []
        accepted: list[dict[str, object]] = []
        generation_error: ModelAdapterError | None = None
        for attempt in range(1, 4):
            try:
                chunks = model.stream_text(system=system, prompt=prompt, cancel=cancel)
                while True:
                    chunk, finished = _next_model_chunk(chunks, runtime)
                    if finished:
                        break
                    assert chunk is not None
                    buffer += chunk
                    complete_lines = buffer.split("\n")
                    buffer = complete_lines.pop()
                    for raw_line in complete_lines:
                        line = raw_line.strip()
                        if not line:
                            continue
                        lines.append(line)
                        if len(lines) > MAX_BLOCKS:
                            raise ModelAdapterError(
                                "ANSWER_REJECTED", "回答分段过多", retryable=False
                            )
                        if not _review_and_persist_line(
                            engine,
                            run_id,
                            model,
                            runtime,
                            line=line,
                            index=len(accepted),
                            snapshot=snapshot,
                            question=question,
                            evidence_rows=evidence_rows,
                            evidence_by_id=evidence_by_id,
                            accepted=accepted,
                        ):
                            _terminal(engine, run_id, status="cancelled")
                            return
                if buffer.strip():
                    lines.append(buffer.strip())
                    if len(lines) > MAX_BLOCKS:
                        raise ModelAdapterError("ANSWER_REJECTED", "回答分段过多", retryable=False)
                    if not _review_and_persist_line(
                        engine,
                        run_id,
                        model,
                        runtime,
                        line=buffer.strip(),
                        index=len(accepted),
                        snapshot=snapshot,
                        question=question,
                        evidence_rows=evidence_rows,
                        evidence_by_id=evidence_by_id,
                        accepted=accepted,
                    ):
                        _terminal(engine, run_id, status="cancelled")
                        return
                if cancel.is_set():
                    _terminal(engine, run_id, status="cancelled")
                    return
                if not lines:
                    raise ModelAdapterError("ANSWER_REJECTED", "模型未返回有效回答", retryable=True)
                with Session(engine) as session:
                    step = session.get(RunStep, step_id)
                    if step is not None:
                        _complete_step(session, step, {"lineCount": len(lines)})
                        session.commit()
                generation_error = None
                break
            except ModelAdapterError as error:
                with Session(engine) as session:
                    step = session.get(RunStep, step_id)
                    if step is not None and step.status == "running":
                        _fail_step(session, step, error)
                        session.commit()
                generation_error = error
                if accepted or not error.retryable or attempt == 3:
                    raise
                buffer = ""
                lines = []
                with Session(engine) as session:
                    run = session.get(AgentRun, run_id)
                    if run is None or run.status != "running":
                        return
                    next_step = _step(
                        session,
                        run,
                        "generate_answer_jsonl",
                        {"evidenceCount": len(evidence_rows), "attempt": attempt + 1},
                    )
                    step_id = next_step.id
        if generation_error is not None:
            raise generation_error
        follow_up = _generate_structured_with_retries(
            engine,
            run_id,
            model,
            runtime,
            name="generate_follow_up",
            system="根据本轮学生问题与已核验回答，给出零到三个简短、开放且不代写结论的追问。",
            prompt=_json({"question": question, "acceptedBlocks": accepted}),
            schema=FollowUpOutput,
            summary={"acceptedBlockCount": len(accepted)},
        )
        memory_summary = "；".join(
            str(item.get("text", "")) for item in accepted if item.get("text")
        )[:500]
        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            if run is not None and run.status == "running":
                message = session.get(Message, run.output_message_id)
                if message is not None:
                    _event(
                        session,
                        run,
                        "answer.meta",
                        {
                            "messageId": message.id,
                            "followUpQuestions": follow_up.follow_up_questions,
                            "phase": "answer",
                            "memorySummary": memory_summary,
                        },
                    )
                    session.commit()
        _terminal(
            engine,
            run_id,
            status="completed",
            meta={
                "followUpQuestions": follow_up.follow_up_questions,
                "memorySummary": memory_summary,
            },
        )
    except AppError as exc:
        _terminal(
            engine,
            run_id,
            status="failed",
            error=ModelAdapterError(exc.code, exc.message, retryable=exc.retryable),
        )
    except ModelAdapterError as error:
        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            running_step = session.exec(
                select(RunStep).where(RunStep.run_id == run_id, RunStep.status == "running")
            ).first()
            if running_step is not None:
                _fail_step(session, running_step, error)
                session.commit()
        _terminal(engine, run_id, status="failed", error=error)
    finally:
        runtime.unregister(run_id)


def start_summary(
    session: Session,
    user: User,
    session_id: str,
    settings: Settings,
    *,
    path: str,
    idempotency_key: str | None,
):
    _, role_session = _task_and_session(session, user, session_id, write=True)
    _ensure_can_run(role_session)
    reservation = idempotency.begin(
        session,
        user_id=user.id,
        method="POST",
        path=path,
        key=idempotency_key,
        digest=idempotency.request_hash("POST", path, {}),
    )
    if reservation.replay is not None:
        return (
            materials.RunView.model_validate(reservation.replay.body),
            reservation.replay.status,
            str(reservation.replay.body["id"]),
        )
    active = session.exec(
        select(AgentRun).where(
            AgentRun.session_id == role_session.id,
            AgentRun.status == "running",
            AgentRun.kind.in_(("chat", "summary")),
        )
    ).first()
    if active is not None:
        raise AppError("RUN_ALREADY_ACTIVE", "当前回答尚未结束", 409)
    now = _now()
    run = AgentRun(
        id=str(uuid4()),
        actor_id=user.id,
        task_id=role_session.task_id,
        version_id=role_session.version_id,
        version_revision=role_session.version_revision,
        kind="summary",
        status="running",
        session_id=role_session.id,
        source_id=None,
        input_message_id=None,
        output_message_id=None,
        retry_of_run_id=None,
        step_count=0,
        max_steps=settings.run_max_steps,
        deadline_at=_future(settings.run_timeout_seconds),
        cancel_requested_at=None,
        terminal_reason=None,
        execution_config_json=_json({"model": settings.llm_model, "promptVersion": PROMPT_VERSION}),
        result_json=None,
        error_json=None,
        created_at=now,
        finished_at=None,
    )
    session.add(run)
    session.flush()
    _event(session, run, "run.started", {"kind": "summary", "status": "running"})
    data = materials.run_view(run)
    idempotency.complete(
        session, reservation, status=202, body=data.model_dump(by_alias=True), resource_id=run.id
    )
    session.commit()
    return data, 202, run.id


def process_summary(
    engine: Any, settings: Settings, model: DialogueModel, runtime: WorkflowRuntime, run_id: str
) -> None:
    cancel = runtime.register(run_id)
    try:
        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            if run is None or run.status != "running":
                return
            role_session = session.get(RoleSession, run.session_id)
            if role_session is None:
                return
            rows = session.exec(
                select(Message)
                .where(
                    Message.session_id == role_session.id,
                    ((Message.speaker == "user") | (Message.status == "complete")),
                )
                .order_by(Message.seq)
            ).all()
            step = _step(session, run, "prepare_summary", {"messageCount": len(rows)})
            step_id = step.id
            prompt = _json(
                {
                    "existingSummary": _load(role_session.summary_json, {}),
                    "messages": [
                        {"seq": row.seq, "speaker": row.speaker, "text": row.text} for row in rows
                    ],
                }
            )
            through_seq = max((row.seq for row in rows), default=0)
        with Session(engine) as session:
            step = session.get(RunStep, step_id)
            if step is not None:
                _complete_step(session, step, {"prepared": True})
                session.commit()
        output = _generate_structured_with_retries(
            engine,
            run_id,
            model,
            runtime,
            name="summarize_conversation",
            system=(
                "整理已完成的探究对话。区分学生观点、已核验资料事实、未解决问题和"
                "已有追问；不得吸收部分或失败回答，不得改写角色知识边界。"
            ),
            prompt=prompt,
            schema=ConversationSummaryOutput,
            summary={"messageCount": len(rows)},
        )
        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            role_session = session.get(RoleSession, run.session_id) if run is not None else None
            step = session.get(RunStep, step_id)
            if run is None or role_session is None or run.status != "running":
                return
            if run.cancel_requested_at is not None or cancel.is_set():
                _terminal(engine, run_id, status="cancelled")
                return
            summary = output.model_dump(by_alias=True, mode="json")
            role_session.summary_json = _json(summary)
            role_session.summary_through_seq = through_seq
            role_session.updated_at = _now()
            if step is not None:
                _complete_step(session, step, {"throughSeq": through_seq})
            result = SummaryResult(
                summary="；".join(output.student_views + output.verified_facts),
                unresolved_questions=output.unresolved_questions,
            ).model_dump(by_alias=True)
            run.status = "completed"
            run.result_json = _json(result)
            run.finished_at = _now()
            _event(session, run, "run.completed", {"result": result})
            session.commit()
    except (AppError, ModelAdapterError) as caught:
        error = (
            caught
            if isinstance(caught, ModelAdapterError)
            else ModelAdapterError(caught.code, caught.message, retryable=caught.retryable)
        )
        _terminal(engine, run_id, status="failed", error=error)
    finally:
        runtime.unregister(run_id)


def retry_chat(
    session: Session,
    user: User,
    run_id: str,
    settings: Settings,
    *,
    path: str,
    idempotency_key: str | None,
):
    original = session.get(AgentRun, run_id)
    if original is None or original.actor_id != user.id or original.kind != "chat":
        raise AppError("NOT_FOUND", "资源不存在", 404)
    _, role_session = _task_and_session(session, user, original.session_id, write=True)
    _ensure_can_run(role_session)
    reservation = idempotency.begin(
        session,
        user_id=user.id,
        method="POST",
        path=path,
        key=idempotency_key,
        digest=idempotency.request_hash("POST", path, {}),
    )
    if reservation.replay is not None:
        data = materials.RunView.model_validate(reservation.replay.body)
        return data, reservation.replay.status, data.id
    if original.status not in {"failed", "cancelled"}:
        raise AppError("RETRY_NOT_ALLOWED", "当前运行不可重试", 409)
    latest = session.exec(
        select(AgentRun)
        .where(AgentRun.input_message_id == original.input_message_id, AgentRun.kind == "chat")
        .order_by(AgentRun.created_at.desc())
    ).first()
    latest_user = session.exec(
        select(Message)
        .where(Message.session_id == role_session.id, Message.speaker == "user")
        .order_by(Message.seq.desc())
    ).first()
    if (
        latest is None
        or latest.id != original.id
        or latest_user is None
        or (latest_user.id != original.input_message_id)
    ):
        raise AppError("RETRY_NOT_ALLOWED", "已有后续问题或重试", 409)
    active = session.exec(
        select(AgentRun).where(
            AgentRun.session_id == role_session.id,
            AgentRun.status == "running",
            AgentRun.kind.in_(("chat", "summary")),
        )
    ).first()
    if active is not None:
        raise AppError("RUN_ALREADY_ACTIVE", "当前回答尚未结束", 409)
    old_output = session.get(Message, original.output_message_id)
    if old_output is None:
        raise AppError("RETRY_NOT_ALLOWED", "原回答不存在", 409)
    max_seq = (
        session.exec(
            select(func.max(Message.seq)).where(Message.session_id == role_session.id)
        ).one()
        or 0
    )
    now = _now()
    output = Message(
        id=str(uuid4()),
        session_id=role_session.id,
        seq=max_seq + 1,
        speaker="assistant",
        status="pending",
        text="",
        blocks_json="[]",
        meta_json="{}",
        run_id=None,
        supersedes_message_id=old_output.id,
        created_at=now,
        updated_at=now,
    )
    output.run_id = str(uuid4())
    new_run = _new_chat_run(
        session, user, role_session, latest_user, output, settings, retry_of=original.id
    )
    data = materials.run_view(new_run)
    idempotency.complete(
        session,
        reservation,
        status=202,
        body=data.model_dump(by_alias=True),
        resource_id=new_run.id,
    )
    session.commit()
    return data, 202, new_run.id


def fail_interrupted_dialogue_runs(engine: Any) -> int:
    with Session(engine) as session:
        rows = session.exec(
            select(AgentRun).where(
                AgentRun.kind.in_(("chat", "summary")), AgentRun.status == "running"
            )
        ).all()
        ids = [row.id for row in rows]
    error = ModelAdapterError("PROCESS_INTERRUPTED", "服务重启中断了运行", retryable=True)
    for run_id in ids:
        _terminal(engine, run_id, status="failed", error=error)
    return len(ids)
