"""P5 deterministic teacher aggregates, evidence drill-down, reviews, and HTML export."""

from __future__ import annotations

import hashlib
import html
import json
from uuid import uuid4

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.errors import AppError
from app.db.models import (
    Citation,
    Evidence,
    LearningEvent,
    LearningReport,
    Message,
    ReportCorrection,
    ReviewRecord,
    RoleSession,
    Source,
    Submission,
    Task,
    TaskVersion,
    User,
)
from app.schemas.contracts import ReportContent, ReportMetrics
from app.schemas.p5_dtos import (
    ClassroomSummary,
    CoverageView,
    EvaluationRequest,
    KPIView,
    ProgressView,
    ReportDetailItem,
    ReportDetails,
    StudentReportRow,
    TeacherReport,
    TeachingReviewPage,
    TeachingReviewView,
    TeachingSuggestion,
    VersionLabel,
)
from app.services import dialogue, learning

METRICS = {
    "expressionCount",
    "evidenceSeekingCount",
    "sourceViewCount",
    "judgmentCount",
    "reflectionCount",
}


def _owner_task(session: Session, user: User, task_id: str) -> Task:
    task = session.get(Task, task_id)
    if user.role != "teacher" or task is None or task.owner_id != user.id:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    return task


def _scope_versions(
    session: Session, task: Task, scope: str, version_id: str | None
) -> tuple[list[TaskVersion], str | None]:
    published = session.exec(
        select(TaskVersion)
        .where(TaskVersion.task_id == task.id, TaskVersion.status == "published")
        .order_by(TaskVersion.version_no)
    ).all()
    if scope == "latest":
        return [
            row for row in published if row.id == task.current_published_version_id
        ], task.current_published_version_id
    if scope == "all":
        if version_id is not None:
            raise AppError("VALIDATION_ERROR", "all 范围不能指定版本", 422)
        return published, None
    if scope != "version" or version_id is None:
        raise AppError("VALIDATION_ERROR", "version 范围需要 versionId", 422)
    selected = [row for row in published if row.id == version_id]
    if not selected:
        raise AppError("NOT_FOUND", "发布版本不存在", 404)
    return selected, version_id


def _rows(session: Session, task: Task, versions: list[TaskVersion]):
    ids = [row.id for row in versions]
    if not ids:
        return []
    return session.exec(
        select(RoleSession, User, TaskVersion)
        .join(User, User.id == RoleSession.owner_id)
        .join(TaskVersion, TaskVersion.id == RoleSession.version_id)
        .where(
            RoleSession.task_id == task.id,
            RoleSession.mode == "student",
            RoleSession.version_id.in_(ids),
        )
        .order_by(TaskVersion.version_no.desc(), User.display_name, RoleSession.id)
    ).all()


def _latest_ready(session: Session, role_session: RoleSession):
    reports = session.exec(
        select(LearningReport)
        .where(LearningReport.session_id == role_session.id)
        .order_by(LearningReport.input_revision.desc(), LearningReport.report_no.desc())
    ).all()
    desired = "final" if role_session.status == "ended" else "live"
    current = next((row for row in reports if row.kind == desired), None)
    ready = next((row for row in reports if row.status == "ready"), None)
    return current, ready


def _freshness(current: LearningReport | None, role_session: RoleSession) -> str:
    if current is None:
        return "empty"
    if current.status in {"queued", "generating", "superseded"}:
        return "updating"
    if current.status == "failed":
        return "failed"
    return "current" if current.input_revision == role_session.learning_revision else "updating"


def _session_metrics(
    session: Session, role_session: RoleSession, ready: LearningReport | None
) -> ReportMetrics:
    expression = session.exec(
        select(func.count(Message.id)).where(
            Message.session_id == role_session.id, Message.speaker == "user"
        )
    ).one()
    events = session.exec(
        select(LearningEvent).where(LearningEvent.session_id == role_session.id)
    ).all()
    source_count = (
        len({row.source_id for row in events if row.event_type == "source_open"})
        if learning._tracking(role_session) != "unavailable"
        else None
    )
    stance_count = len({row.message_id for row in events if row.event_type == "stance"})
    if ready is None:
        return ReportMetrics(
            expression_count=expression,
            evidence_seeking_count=None,
            source_view_count=source_count,
            judgment_count=None,
            reflection_count=None,
        )
    content = ReportContent.model_validate(learning._load(ready.content_json, {}))
    evidence = {str(item.message_id) for item in content.signals if "evidence_seeking" in item.tags}
    judgment = {str(item.message_id) for item in content.signals if "judgment" in item.tags}
    reflection = {str(item.message_id) for item in content.signals if "reflection" in item.tags}
    return ReportMetrics(
        expression_count=expression,
        evidence_seeking_count=len(evidence),
        source_view_count=source_count,
        judgment_count=len(judgment) + stance_count,
        reflection_count=len(reflection),
    )


def _snapshot(session: Session, task: Task, scope: str, version_id: str | None):
    versions, effective_version = _scope_versions(session, task, scope, version_id)
    rows = _rows(session, task, versions)
    records = []
    for role_session, _, _ in rows:
        _, ready = _latest_ready(session, role_session)
        event_version = session.exec(
            select(func.coalesce(func.max(LearningEvent.row_version), 0)).where(
                LearningEvent.session_id == role_session.id
            )
        ).one()
        correction_count = session.exec(
            select(func.count(ReportCorrection.id)).where(
                ReportCorrection.session_id == role_session.id
            )
        ).one()
        records.append((role_session, ready, event_version, correction_count))
    token_value = {
        "scope": scope,
        "versionId": effective_version,
        "sessions": [
            {
                "sessionId": row.id,
                "learningRevision": row.learning_revision,
                "reportId": ready.id if ready else None,
                "eventVersion": event_version,
                "correctionCount": correction_count,
            }
            for row, ready, event_version, correction_count in records
        ],
    }
    token = hashlib.sha256(
        json.dumps(token_value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return versions, rows, records, token


def teacher_report(
    session: Session,
    user: User,
    task_id: str,
    *,
    scope: str,
    version_id: str | None,
    state: str,
    limit: int,
    cursor: str | None,
) -> TeacherReport:
    task = _owner_task(session, user, task_id)
    versions, rows, records, token = _snapshot(session, task, scope, version_id)
    record_by_id = {
        row.id: (ready, correction_count) for row, ready, _, correction_count in records
    }
    session_metrics = {
        row.id: _session_metrics(session, row, record_by_id[row.id][0]) for row, _, _ in rows
    }
    aggregate: dict[str, int | None] = {
        "expression_count": sum(item.expression_count or 0 for item in session_metrics.values()),
        "source_view_count": (
            sum(
                item.source_view_count or 0
                for item in session_metrics.values()
                if item.source_view_count is not None
            )
            if any(item.source_view_count is not None for item in session_metrics.values())
            else None
        ),
    }
    for field in ("evidence_seeking_count", "judgment_count", "reflection_count"):
        known = [
            getattr(item, field)
            for item in session_metrics.values()
            if getattr(item, field) is not None
        ]
        aggregate[field] = sum(known) if known else None
    ready_count = sum(1 for _, ready, _, _ in records if ready is not None)
    current_count = sum(
        1
        for role_session, ready, _, _ in records
        if ready is not None and ready.input_revision == role_session.learning_revision
    )
    completed_reports = 0
    for role_session, ready, _, _ in records:
        final_ready = ready is not None and ready.kind == "final" and ready.status == "ready"
        legacy = session.exec(
            select(Submission.id).where(
                Submission.session_id == role_session.id, Submission.status == "submitted"
            )
        ).first()
        if role_session.status == "ended" and (final_ready or legacy is not None):
            completed_reports += 1
    filtered = rows if state == "all" else [item for item in rows if item[0].status == state]
    if cursor:
        filtered = [item for item in filtered if item[0].id > cursor]
    page = filtered[: limit + 1]
    more = len(page) > limit
    page = page[:limit]
    students = []
    for role_session, student, version in page:
        current, ready = _latest_ready(session, role_session)
        students.append(
            StudentReportRow(
                user_id=student.id,
                display_name=student.display_name,
                session_id=role_session.id,
                version_id=version.id,
                version_no=version.version_no,
                status=role_session.status,
                metrics=session_metrics[role_session.id],
                report_id=ready.id if ready else None,
                report_status=current.status if current else None,
                report_freshness=_freshness(current, role_session),
                source_tracking=learning._tracking(role_session),
                correction_count=record_by_id[role_session.id][1],
            )
        )
    active = sum(1 for row, _, _ in rows if row.status == "active")
    ended = len(rows) - active
    participant_count = len({row.owner_id for row, _, _ in rows})
    summary = (
        f"当前范围有 {participant_count} 位学生开展 {len(rows)} 次探究，"
        f"其中 {ended} 次已结束，已整理 {ready_count} 份可读报告。"
        if rows
        else "当前范围还没有学生探究记录。"
    )
    missing_ready = len(rows) - ready_count
    suggestions = []
    if missing_ready:
        suggestions.append(
            TeachingSuggestion(
                text=(
                    f"有 {missing_ready} 次探究的语义报告尚未就绪；"
                    "可先查看学生原话，不把未知计为零。"
                ),
                session_ids=[row.id for row, _, _ in rows if record_by_id[row.id][0] is None],
                message_ids=[],
            )
        )
    elif rows:
        suggestions.append(
            TeachingSuggestion(
                text=(
                    "可以从学生已经表达的判断与依据出发，继续讨论资料能说明什么、仍不能确定什么。"
                ),
                session_ids=[row.id for row, _, _ in rows],
                message_ids=[],
            )
        )
    complete = sum(1 for row, _, _ in rows if learning._tracking(row) == "complete")
    partial = sum(1 for row, _, _ in rows if learning._tracking(row) == "partial")
    return TeacherReport(
        task_id=task.id,
        scope=scope,
        version_id=version_id,
        versions=[VersionLabel(id=row.id, version_no=row.version_no) for row in versions],
        as_of=dialogue._now(),
        aggregate_token=token,
        kpis=KPIView(
            participant_count=participant_count,
            session_count=len(rows),
            completed_turns=sum(row.completed_turns for row, _, _ in rows),
            completed_report_count=completed_reports,
        ),
        progress=ProgressView(active_sessions=active, ended_sessions=ended),
        metrics=ReportMetrics(**aggregate),
        coverage=CoverageView(
            total_sessions=len(rows),
            ready_report_sessions=ready_count,
            current_report_sessions=current_count,
            source_tracked_sessions=complete,
            partial_source_sessions=partial,
            unavailable_source_sessions=len(rows) - complete - partial,
        ),
        classroom_summary=ClassroomSummary(
            text=summary, session_ids=[row.id for row, _, _ in rows]
        ),
        suggestions=suggestions,
        students=students,
        next_cursor=page[-1][0].id if more else None,
    )


def report_details(
    session: Session,
    user: User,
    task_id: str,
    *,
    scope: str,
    version_id: str | None,
    metric: str,
    aggregate_token: str,
    session_id: str | None,
    limit: int,
    cursor: str | None,
) -> ReportDetails:
    if metric not in METRICS:
        raise AppError("VALIDATION_ERROR", "metric 无效", 422)
    task = _owner_task(session, user, task_id)
    _, rows, _, token = _snapshot(session, task, scope, version_id)
    if token != aggregate_token:
        raise AppError("REPORT_CHANGED", "报告数据已变化，请刷新后重试", 409)
    if session_id is not None:
        rows = [item for item in rows if item[0].id == session_id]
        if not rows:
            raise AppError("NOT_FOUND", "会话不在当前报告范围", 404)
    items: list[ReportDetailItem] = []
    tags = {
        "evidenceSeekingCount": "evidence_seeking",
        "reflectionCount": "reflection",
        "judgmentCount": "judgment",
    }
    for role_session, student, _ in rows:
        _, ready = _latest_ready(session, role_session)
        if metric == "expressionCount":
            messages = session.exec(
                select(Message)
                .where(Message.session_id == role_session.id, Message.speaker == "user")
                .order_by(Message.seq)
            ).all()
            items.extend(
                ReportDetailItem(
                    session_id=role_session.id,
                    student_name=student.display_name,
                    message_id=row.id,
                    quote=row.text,
                )
                for row in messages
            )
        elif metric in tags and ready:
            content = ReportContent.model_validate(learning._load(ready.content_json, {}))
            for signal in content.signals:
                if tags[metric] in signal.tags:
                    items.append(
                        ReportDetailItem(
                            session_id=role_session.id,
                            student_name=student.display_name,
                            report_id=ready.id,
                            message_id=str(signal.message_id),
                            quote=signal.quote,
                        )
                    )
            if metric == "judgmentCount":
                for event in session.exec(
                    select(LearningEvent).where(
                        LearningEvent.session_id == role_session.id,
                        LearningEvent.event_type == "stance",
                    )
                ).all():
                    items.append(
                        ReportDetailItem(
                            session_id=role_session.id,
                            student_name=student.display_name,
                            report_id=ready.id,
                            message_id=event.message_id,
                            stance_value=event.value,
                        )
                    )
        elif metric == "sourceViewCount":
            for _event, source in session.exec(
                select(LearningEvent, Source)
                .join(Source, Source.id == LearningEvent.source_id)
                .where(
                    LearningEvent.session_id == role_session.id,
                    LearningEvent.event_type == "source_open",
                )
            ).all():
                items.append(
                    ReportDetailItem(
                        session_id=role_session.id,
                        student_name=student.display_name,
                        source_id=source.id,
                        source_name=source.file_name,
                    )
                )
    items.sort(key=lambda item: (item.session_id, item.message_id or item.source_id or ""))
    start = int(cursor) if cursor else 0
    page = items[start : start + limit + 1]
    more = len(page) > limit
    page = page[:limit]
    return ReportDetails(
        items=page,
        next_cursor=str(start + limit) if more else None,
        aggregate_token=token,
    )


def add_evaluation(
    session: Session, user: User, session_id: str, payload: EvaluationRequest
) -> str:
    role_session = session.get(RoleSession, session_id)
    task = session.get(Task, role_session.task_id) if role_session else None
    if role_session is None or task is None or user.role != "teacher" or task.owner_id != user.id:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    messages = session.exec(
        select(Message.id).where(
            Message.session_id == role_session.id, Message.id.in_(payload.message_ids)
        )
    ).all()
    if len(messages) != len(set(payload.message_ids)):
        raise AppError("VALIDATION_ERROR", "评阅消息不属于当前会话", 422)
    review_id = str(uuid4())
    session.add(
        ReviewRecord(
            id=review_id,
            task_id=task.id,
            version_id=role_session.version_id,
            version_revision=role_session.version_revision,
            kind="evaluation",
            session_id=role_session.id,
            run_id=None,
            message_id=None,
            block_index=None,
            actor_id=user.id,
            passed=None,
            result_json=json.dumps(
                {
                    "messageIds": payload.message_ids,
                    "results": payload.results.model_dump(by_alias=True, exclude_none=True),
                    "note": payload.note.strip(),
                },
                ensure_ascii=False,
            ),
            issues_json="[]",
            created_at=dialogue._now(),
        )
    )
    session.flush()
    return review_id


def list_reviews(
    session: Session, user: User, session_id: str, *, limit: int, cursor: str | None
) -> TeachingReviewPage:
    role_session = session.get(RoleSession, session_id)
    task = session.get(Task, role_session.task_id) if role_session else None
    if role_session is None or task is None or user.role != "teacher" or task.owner_id != user.id:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    statement = select(ReviewRecord).where(
        ReviewRecord.session_id == role_session.id,
        ReviewRecord.kind.in_(("evaluation", "answer_check")),
    )
    if cursor:
        statement = statement.where(ReviewRecord.id > cursor)
    rows = session.exec(statement.order_by(ReviewRecord.id).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    items = []
    for row in rows:
        data = learning._load(row.result_json, {})
        if row.kind == "evaluation":
            summary = str(data.get("note") or "教师已添加一条教学评阅。")
            category = "教学评阅"
        else:
            issues = learning._load(row.issues_json, [])
            summary = (
                "角色回答已通过来源与边界核对" if row.passed else "回答存在值得继续讨论的边界问题"
            )
            if issues:
                messages = [
                    str(item.get("message", "")) for item in issues if isinstance(item, dict)
                ]
                summary = "；".join(filter(None, messages)) or summary
            category = "回答观察"
        items.append(
            TeachingReviewView(
                id=row.id,
                category=category,
                summary=summary,
                message_id=row.message_id,
                block_index=row.block_index,
                citations=[],
            )
        )
    return TeachingReviewPage(items=items, next_cursor=rows[-1].id if more and rows else None)


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _source_location(evidence: Evidence) -> str:
    if evidence.page_no is not None:
        return f"第 {evidence.page_no} 页"
    return f"第 {evidence.start_line}-{evidence.end_line} 行"


def render_export(
    session: Session,
    user: User,
    task_id: str,
    *,
    scope: str,
    version_id: str | None,
    aggregate_token: str,
) -> str:
    report = teacher_report(
        session,
        user,
        task_id,
        scope=scope,
        version_id=version_id,
        state="all",
        limit=100,
        cursor=None,
    )
    if report.aggregate_token != aggregate_token:
        raise AppError("REPORT_CHANGED", "报告数据已变化，请刷新后重试", 409)
    rows_html = []
    for row in report.students:
        envelope = learning.report_envelope(session, user, row.session_id)
        ready = envelope.latest_ready_report
        summary = ready.content.summary.text if ready and ready.content else "报告尚未整理完成。"
        corrections = "".join(
            f"<blockquote>{_escape(item.text)}</blockquote>" for item in envelope.corrections
        )
        messages = session.exec(
            select(Message).where(Message.session_id == row.session_id).order_by(Message.seq)
        ).all()
        quote_parts = []
        for item in messages:
            if not item.text.strip():
                continue
            label = "学生原话" if item.speaker == "user" else "角色表达"
            quote_parts.append(f"<p><strong>{label}：</strong>{_escape(item.text)}</p>")
        source_rows = session.exec(
            select(Citation, Evidence, Source)
            .join(Evidence, Evidence.id == Citation.evidence_id)
            .join(Source, Source.id == Evidence.source_id)
            .join(Message, Message.id == Citation.message_id)
            .where(Message.session_id == row.session_id)
        ).all()
        source_parts = []
        for citation, evidence, source in source_rows:
            source_parts.append(
                f"<li>{_escape(source.file_name)} · {_escape(_source_location(evidence))}"
                f"<blockquote>{_escape(citation.quote)}</blockquote></li>"
            )
        quotes = "".join(quote_parts) or "<p>暂无对话记录。</p>"
        sources = "".join(source_parts) or "<li>暂无已展示引用。</li>"
        rows_html.append(
            "<section>"
            f"<h2>{_escape(row.display_name)} · 第 {row.version_no} 次发布</h2>"
            f"<p>{_escape(summary)}</p>"
            f"<p>状态：{_escape(row.status)}；表达 "
            f"{_escape(row.metrics.expression_count)} 次；报告："
            f"{_escape(row.report_status or '未生成')}</p>"
            f"{corrections}<details><summary>查看原话与角色表达</summary>{quotes}</details>"
            f"<details><summary>查看引用来源</summary><ul>{sources}</ul></details>"
            "</section>"
        )
    metrics = report.metrics
    suggestions = "".join(f"<p>{_escape(item.text)}</p>" for item in report.suggestions)
    metric_values = [
        metrics.expression_count,
        metrics.evidence_seeking_count if metrics.evidence_seeking_count is not None else "整理中",
        metrics.source_view_count if metrics.source_view_count is not None else "未记录",
        metrics.judgment_count if metrics.judgment_count is not None else "整理中",
        metrics.reflection_count if metrics.reflection_count is not None else "整理中",
    ]
    metric_cells = "".join(f"<td>{_escape(value)}</td>" for value in metric_values)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy"
 content="default-src 'none'; style-src 'unsafe-inline';
 base-uri 'none'; form-action 'none'">
<title>知境 · 教学报告</title><style>
body{{max-width:1050px;margin:2rem auto;padding:1rem;color:#263b2f;
background:#f7f8f4;font:15px/1.8 system-ui}}
section,.card{{background:#fff;border:1px solid #e2e7dc;border-radius:12px;
padding:1.5rem;margin:1rem 0}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem}}
blockquote{{border-left:3px solid #367a42;margin:1rem 0;padding:.5rem 1rem;
background:#f7f8f4;white-space:pre-wrap}}
th,td{{padding:.6rem;border-bottom:1px solid #e2e7dc;text-align:left}}
table{{width:100%;border-collapse:collapse}}
@media(max-width:700px){{.grid{{grid-template-columns:1fr 1fr}}}}
</style></head><body><h1>知境 · 教学报告</h1>
<p>范围：{_escape(scope)}；生成时间：{_escape(report.as_of)}</p>
<div class="grid"><div class="card">参与学生<br>
<strong>{report.kpis.participant_count}</strong></div>
<div class="card">探究次数<br><strong>{report.kpis.session_count}</strong></div>
<div class="card">对话轮数<br><strong>{report.kpis.completed_turns}</strong></div>
<div class="card">已完成报告<br><strong>{report.kpis.completed_report_count}</strong></div></div>
<section><h2>课堂小结</h2><p>{_escape(report.classroom_summary.text)}</p>{suggestions}</section>
<section><h2>行为统计</h2><table><tr><th>表达想法</th><th>寻找依据</th><th>查阅资料</th><th>作出判断</th><th>反思修正</th></tr>
<tr>{metric_cells}</tr></table><p>次数来自实际表达、报告信号和来源/判断操作，不代表成绩或能力。</p></section>
{"".join(rows_html)}</body></html>"""
