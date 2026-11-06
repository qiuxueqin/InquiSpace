"""P2 source storage, parsing, retrieval, and authorization services."""

from __future__ import annotations

import base64
import hashlib
import json
import multiprocessing
import os
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

import jieba
from rank_bm25 import BM25Okapi
from sqlalchemy import delete, func, update
from sqlmodel import Session, select

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models import (
    AgentRun,
    Citation,
    Evidence,
    Message,
    RoleSession,
    RunEvent,
    Source,
    Task,
    TaskVersion,
    User,
    VersionSource,
)
from app.schemas.material_dtos import (
    DetachSourceResult,
    EvidencePage,
    EvidenceSearchResult,
    EvidenceView,
    LinkSourceResult,
    RunErrorView,
    RunView,
    SourceView,
    TextLinesView,
    UploadSourceResult,
)
from app.tools.material_parser import PARSER_VERSION, ParseFailure, parse_material

_PDF_SIGNATURE = b"%PDF-"
_SAFE_FILE_RE = re.compile(r"[^\w.()\-一-鿿 ]+", re.UNICODE)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _future(seconds: int) -> str:
    return (
        (datetime.now(UTC) + timedelta(seconds=seconds))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _owner_version(
    session: Session, user: User, version_id: str, *, draft: bool = False
) -> TaskVersion:
    if user.role != "teacher" or not user.is_active:
        raise AppError("FORBIDDEN", "无权执行此操作", 403)
    version = session.get(TaskVersion, version_id)
    if version is None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    task = session.get(Task, version.task_id)
    if task is None or task.owner_id != user.id:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    if draft and version.status != "draft":
        raise AppError("VERSION_IMMUTABLE", "已发布版本不可修改", 409)
    if task.status != "active" and draft:
        raise AppError("TASK_ARCHIVED", "任务已归档", 409)
    return version


def _owner_source(session: Session, user: User, source_id: str) -> Source:
    source = session.get(Source, source_id)
    if source is None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    task = session.get(Task, source.task_id)
    if task is None or task.owner_id != user.id or user.role != "teacher":
        raise AppError("NOT_FOUND", "资源不存在", 404)
    return source


def _student_source_access(session: Session, user: User, source: Source) -> bool:
    if user.role != "student" or not user.is_active:
        return False
    statement = (
        select(Citation.id)
        .join(Evidence, Evidence.id == Citation.evidence_id)
        .join(Message, Message.id == Citation.message_id)
        .join(RoleSession, RoleSession.id == Message.session_id)
        .join(Task, Task.id == RoleSession.task_id)
        .where(
            Evidence.source_id == source.id,
            RoleSession.owner_id == user.id,
            RoleSession.mode == "student",
            Task.status == "active",
        )
    )
    return session.exec(statement).first() is not None


def accessible_source(session: Session, user: User, source_id: str) -> Source:
    source = session.get(Source, source_id)
    if source is None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    task = session.get(Task, source.task_id)
    if task is not None and task.owner_id == user.id and user.role == "teacher":
        return source
    if _student_source_access(session, user, source):
        return source
    raise AppError("NOT_FOUND", "资源不存在", 404)


def accessible_evidence(session: Session, user: User, evidence_id: str) -> Evidence:
    evidence = session.get(Evidence, evidence_id)
    if evidence is None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    source = accessible_source(session, user, evidence.source_id)
    if user.role == "student":
        cited = session.exec(
            select(Citation.id)
            .join(Message, Message.id == Citation.message_id)
            .join(RoleSession, RoleSession.id == Message.session_id)
            .where(Citation.evidence_id == evidence.id, RoleSession.owner_id == user.id)
        ).first()
        if cited is None:
            raise AppError("NOT_FOUND", "资源不存在", 404)
    if source.id != evidence.source_id:  # pragma: no cover - defensive
        raise AppError("NOT_FOUND", "资源不存在", 404)
    return evidence


def source_view(source: Source) -> SourceView:
    warnings = _load(source.warnings_json, [])
    if not isinstance(warnings, list):
        warnings = []
    parse_error = _load(source.parse_error_json, None)
    if not isinstance(parse_error, dict):
        parse_error = None
    return SourceView(
        id=source.id,
        task_id=source.task_id,
        file_name=source.file_name,
        file_type=source.file_type,
        byte_size=source.byte_size,
        sha256=source.sha256,
        status=source.status,
        page_count=source.page_count,
        total_lines=source.total_lines,
        parse_error=parse_error,
        warnings=warnings,
        created_at=source.created_at,
    )


def evidence_view(evidence: Evidence, source: Source) -> EvidenceView:
    if evidence.page_no is not None:
        label = f"{source.file_name} · 第 {evidence.page_no} 页"
    else:
        label = f"{source.file_name} · 第 {evidence.start_line}—{evidence.end_line} 行"
    return EvidenceView(
        id=evidence.id,
        source_id=evidence.source_id,
        text=evidence.text,
        page_no=evidence.page_no,
        paragraph_no=evidence.paragraph_no,
        start_line=evidence.start_line,
        end_line=evidence.end_line,
        disputed=bool(evidence.disputed),
        source_label=label,
    )


def run_view(run: AgentRun) -> RunView:
    error_value = _load(run.error_json, None)
    error = None
    if isinstance(error_value, dict) and error_value.get("code") and error_value.get("message"):
        error = RunErrorView(
            code=str(error_value["code"]),
            message=str(error_value["message"]),
            retryable=bool(error_value.get("retryable", False)),
        )
    action = {
        "parse_material": "解析资料",
        "role_generate": "生成角色候选",
        "role_validate": "检查角色一致性",
        "plan_generate": "生成教学方案",
        "publish_preflight": "准备发布检查",
        "chat": "回答",
        "summary": "整理阶段小结",
        "learning_report": "整理学习报告",
    }.get(run.kind, "处理任务")
    messages = {
        "running": f"正在{action}",
        "completed": f"{action}完成",
        "failed": f"{action}失败",
        "cancelled": f"{action}已取消",
        "waiting_confirmation": "候选已生成，等待确认",
    }
    result_value = _load(run.result_json, None)
    return RunView(
        id=run.id,
        kind=run.kind,
        status=run.status,
        display_message=messages.get(run.status, "资料处理状态已更新"),
        session_id=run.session_id,
        version_id=run.version_id,
        result=result_value if isinstance(result_value, dict) else None,
        error=error,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


def _safe_name(filename: str | None) -> tuple[str, str]:
    if not filename:
        raise AppError("UNSUPPORTED_FILE_TYPE", "文件名无效", 422)
    leaf = Path(filename.replace("\\", "/")).name.strip()
    if not leaf or leaf in {".", ".."}:
        raise AppError("UNSUPPORTED_FILE_TYPE", "文件名无效", 422)
    cleaned = _SAFE_FILE_RE.sub("_", leaf)[:200]
    suffix = Path(cleaned).suffix.lower()
    if suffix not in {".pdf", ".txt"}:
        raise AppError("UNSUPPORTED_FILE_TYPE", "仅支持 PDF 和 UTF-8 TXT", 422)
    return cleaned, suffix[1:]


def _write_upload(file: BinaryIO, settings: Settings) -> tuple[Path, int, str, bytes]:
    temp_dir = settings.data_dir / "uploads" / ".tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    prefix = b""
    fd, raw_path = tempfile.mkstemp(prefix="upload-", dir=temp_dir)
    path = Path(raw_path)
    try:
        with os.fdopen(fd, "wb") as target:
            while chunk := file.read(64 * 1024):
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise AppError("FILE_TOO_LARGE", "文件超过大小限制", 413)
                if len(prefix) < 8:
                    prefix += chunk[: 8 - len(prefix)]
                digest.update(chunk)
                target.write(chunk)
        if total == 0:
            raise AppError("EMPTY_FILE", "文件为空", 422)
        return path, total, digest.hexdigest(), prefix
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _validate_content(file_type: str, prefix: bytes) -> None:
    if file_type == "pdf" and not prefix.startswith(_PDF_SIGNATURE):
        raise AppError("UNSUPPORTED_FILE_TYPE", "文件内容不是 PDF", 422)
    if file_type == "txt" and prefix.startswith(_PDF_SIGNATURE):
        raise AppError("UNSUPPORTED_FILE_TYPE", "文件扩展名与内容不一致", 422)


def _new_event(
    run: AgentRun, seq: int, event_type: str, payload: dict[str, object], now: str
) -> RunEvent:
    return RunEvent(
        id=str(uuid4()),
        run_id=run.id,
        seq=seq,
        event_type=event_type,
        payload_json=_json(payload),
        created_at=now,
    )


def create_upload(
    session: Session,
    user: User,
    version_id: str,
    *,
    expected_revision: int,
    filename: str | None,
    file: BinaryIO,
    settings: Settings,
) -> tuple[UploadSourceResult, str]:
    version = _owner_version(session, user, version_id, draft=True)
    if version.revision != expected_revision:
        raise AppError(
            "REVISION_CONFLICT",
            "内容已变化，请重新载入",
            412,
            details={"currentRevision": version.revision},
        )
    count = session.exec(
        select(func.count())
        .select_from(VersionSource)
        .where(VersionSource.version_id == version.id)
    ).one()
    if count >= settings.max_sources_per_version:
        raise AppError("SOURCE_LIMIT_EXCEEDED", "该版本资料数量已达上限", 422)
    clean_name, file_type = _safe_name(filename)
    temp_path, byte_size, sha256, prefix = _write_upload(file, settings)
    try:
        _validate_content(file_type, prefix)
        source_id = str(uuid4())
        storage_key = f"{version.task_id}/{source_id}.{file_type}"
        destination = settings.data_dir / "uploads" / storage_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_path, destination)
        now = _now()
        source = Source(
            id=source_id,
            task_id=version.task_id,
            uploaded_by=user.id,
            file_name=clean_name,
            file_type=file_type,
            byte_size=byte_size,
            sha256=sha256,
            storage_key=storage_key,
            status="parsing",
            page_count=None,
            total_lines=None,
            parser_version=None,
            parse_error_json=None,
            warnings_json="[]",
            created_at=now,
            updated_at=now,
        )
        new_revision = version.revision + 1
        run = AgentRun(
            id=str(uuid4()),
            actor_id=user.id,
            task_id=version.task_id,
            version_id=version.id,
            version_revision=new_revision,
            kind="parse_material",
            status="running",
            session_id=None,
            source_id=source.id,
            input_message_id=None,
            output_message_id=None,
            retry_of_run_id=None,
            step_count=0,
            max_steps=settings.run_max_steps,
            deadline_at=_future(settings.parse_timeout_seconds),
            cancel_requested_at=None,
            terminal_reason=None,
            execution_config_json=_json({"parserVersion": PARSER_VERSION}),
            result_json=None,
            error_json=None,
            created_at=now,
            finished_at=None,
        )
        session.add(source)
        session.flush()
        session.add(
            VersionSource(
                task_id=version.task_id,
                version_id=version.id,
                source_id=source.id,
                created_at=now,
            )
        )
        session.add(run)
        session.add(
            _new_event(
                run,
                1,
                "run.started",
                {"runId": run.id, "seq": 1, "kind": run.kind, "status": run.status},
                now,
            )
        )
        result = session.execute(
            update(TaskVersion)
            .where(
                TaskVersion.id == version.id,
                TaskVersion.status == "draft",
                TaskVersion.revision == expected_revision,
            )
            .values(
                revision=new_revision,
                validation_status="stale",
                validated_revision=None,
                preview_revision=None,
                content_hash=None,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            raise AppError("REVISION_CONFLICT", "内容已变化，请重新载入", 412)
        session.commit()
        return (
            UploadSourceResult(
                source=source_view(source), run=run_view(run), revision=new_revision
            ),
            run.id,
        )
    except Exception:
        session.rollback()
        temp_path.unlink(missing_ok=True)
        destination_value = locals().get("destination")
        if isinstance(destination_value, Path):
            destination_value.unlink(missing_ok=True)
        raise


def _parse_process(connection: Any, path_text: str, file_type: str, max_pages: int) -> None:
    try:
        connection.send({"ok": True, "data": parse_material(path_text, file_type, max_pages)})
    except ParseFailure as exc:
        connection.send({"ok": False, "code": exc.code, "message": exc.message})
    except Exception:
        connection.send({"ok": False, "code": "PARSE_FAILED", "message": "资料解析失败"})
    finally:
        connection.close()


def _isolated_parse(
    path: Path, file_type: str, max_pages: int, timeout_seconds: int
) -> dict[str, object]:
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_parse_process,
        args=(child, str(path), file_type, max_pages),
        daemon=True,
    )
    process.start()
    child.close()
    try:
        if not parent.poll(timeout_seconds):
            process.terminate()
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)
            return {"ok": False, "code": "PARSE_TIMEOUT", "message": "资料解析超时"}
        try:
            result = parent.recv()
        except EOFError:
            return {"ok": False, "code": "PARSE_FAILED", "message": "资料解析失败"}
        return (
            result
            if isinstance(result, dict)
            else {
                "ok": False,
                "code": "PARSE_FAILED",
                "message": "资料解析失败",
            }
        )
    finally:
        parent.close()
        process.join(timeout=2)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)


def process_parse_run(engine: Any, settings: Settings, run_id: str) -> None:
    with Session(engine) as session:
        run = session.get(AgentRun, run_id)
        if run is None or run.status != "running" or run.source_id is None:
            return
        source = session.get(Source, run.source_id)
        if source is None:
            return
        path = settings.data_dir / "uploads" / source.storage_key
        file_type = source.file_type
    result = _isolated_parse(
        path, file_type, settings.max_pdf_pages, settings.parse_timeout_seconds
    )
    if not result.get("ok"):
        _finish_parse_failure(
            engine,
            run_id,
            str(result.get("code", "PARSE_FAILED")),
            str(result.get("message", "资料解析失败")),
        )
        return
    parsed = result.get("data")
    if not isinstance(parsed, dict):
        _finish_parse_failure(engine, run_id, "PARSE_FAILED", "资料解析失败")
        return
    _finish_parse_success(engine, run_id, parsed)


def _finish_parse_failure(engine: Any, run_id: str, code: str, message: str) -> None:
    with Session(engine) as session:
        run = session.get(AgentRun, run_id)
        if run is None or run.status != "running" or run.source_id is None:
            return
        source = session.get(Source, run.source_id)
        if source is None:
            return
        now = _now()
        error = {"code": code, "message": message, "retryable": code in {"PARSE_TIMEOUT"}}
        source.status = "failed"
        source.parse_error_json = _json(error)
        source.updated_at = now
        run.status = "failed"
        run.step_count = min(run.max_steps, run.step_count + 1)
        run.error_json = _json(error)
        run.finished_at = now
        session.add(
            _new_event(run, 2, "run.failed", {"runId": run.id, "seq": 2, "error": error}, now)
        )
        session.commit()


def _finish_parse_success(engine: Any, run_id: str, parsed: dict[str, object]) -> None:
    with Session(engine) as session:
        run = session.get(AgentRun, run_id)
        if run is None or run.status != "running" or run.source_id is None:
            return
        source = session.get(Source, run.source_id)
        if source is None:
            return
        items = parsed.get("evidence")
        if not isinstance(items, list) or not items:
            session.rollback()
            _finish_parse_failure(engine, run_id, "PARSE_FAILED", "资料中没有可用片段")
            return
        now = _now()
        session.execute(delete(Evidence).where(Evidence.source_id == source.id))
        for ordinal, item in enumerate(items, start=1):
            if not isinstance(item, dict) or not str(item.get("text", "")).strip():
                continue
            session.add(
                Evidence(
                    id=str(uuid4()),
                    source_id=source.id,
                    ordinal=ordinal,
                    text=str(item["text"]),
                    page_no=item.get("pageNo"),
                    paragraph_no=int(item.get("paragraphNo", ordinal)),
                    start_line=item.get("startLine"),
                    end_line=item.get("endLine"),
                    disputed=0,
                    created_at=now,
                )
            )
        source.status = "ready"
        source.page_count = parsed.get("pageCount")
        source.total_lines = parsed.get("totalLines")
        source.parser_version = PARSER_VERSION
        source.parse_error_json = None
        source.warnings_json = _json(parsed.get("warnings", []))
        source.updated_at = now
        linked_drafts = session.exec(
            select(TaskVersion)
            .join(VersionSource, VersionSource.version_id == TaskVersion.id)
            .where(VersionSource.source_id == source.id, TaskVersion.status == "draft")
        ).all()
        for version in linked_drafts:
            version.revision += 1
            version.validation_status = "stale"
            version.validated_revision = None
            version.preview_revision = None
            version.content_hash = None
            version.updated_at = now
        run.status = "completed"
        run.step_count = min(run.max_steps, run.step_count + 1)
        run.result_json = _json({"sourceId": source.id, "status": "ready"})
        run.error_json = None
        run.finished_at = now
        session.add(
            _new_event(
                run,
                2,
                "run.completed",
                {"runId": run.id, "seq": 2, "result": {"sourceId": source.id}},
                now,
            )
        )
        session.commit()


def list_sources(session: Session, user: User, version_id: str) -> list[SourceView]:
    version = _owner_version(session, user, version_id)
    rows = session.exec(
        select(Source)
        .join(VersionSource, VersionSource.source_id == Source.id)
        .where(VersionSource.version_id == version.id)
        .order_by(Source.created_at, Source.id)
    ).all()
    return [source_view(row) for row in rows]


def link_source(
    session: Session,
    user: User,
    version_id: str,
    source_id: str,
    *,
    expected_revision: int,
    settings: Settings,
) -> LinkSourceResult:
    version = _owner_version(session, user, version_id, draft=True)
    if version.revision != expected_revision:
        raise AppError(
            "REVISION_CONFLICT",
            "内容已变化，请重新载入",
            412,
            details={"currentRevision": version.revision},
        )
    source = _owner_source(session, user, source_id)
    if source.task_id != version.task_id:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    if source.status != "ready":
        raise AppError("SOURCE_NOT_READY", "只能复用已解析资料", 409)
    if session.get(VersionSource, (version.id, source.id)) is not None:
        raise AppError("SOURCE_ALREADY_LINKED", "资料已关联", 409)
    count = session.exec(
        select(func.count())
        .select_from(VersionSource)
        .where(VersionSource.version_id == version.id)
    ).one()
    if count >= settings.max_sources_per_version:
        raise AppError("SOURCE_LIMIT_EXCEEDED", "该版本资料数量已达上限", 422)
    now = _now()
    session.add(
        VersionSource(
            task_id=version.task_id, version_id=version.id, source_id=source.id, created_at=now
        )
    )
    version.revision += 1
    version.validation_status = "stale"
    version.validated_revision = None
    version.preview_revision = None
    version.content_hash = None
    version.updated_at = now
    session.commit()
    return LinkSourceResult(source_id=source.id, revision=version.revision)


def detach_source(
    session: Session, user: User, version_id: str, source_id: str, *, expected_revision: int
) -> DetachSourceResult:
    version = _owner_version(session, user, version_id, draft=True)
    if version.revision != expected_revision:
        raise AppError(
            "REVISION_CONFLICT",
            "内容已变化，请重新载入",
            412,
            details={"currentRevision": version.revision},
        )
    link = session.get(VersionSource, (version.id, source_id))
    if link is None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    session.delete(link)
    version.revision += 1
    version.validation_status = "stale"
    version.validated_revision = None
    version.preview_revision = None
    version.content_hash = None
    version.updated_at = _now()
    session.commit()
    return DetachSourceResult(detached=True, revision=version.revision)


def get_source(session: Session, user: User, source_id: str) -> SourceView:
    return source_view(accessible_source(session, user, source_id))


def _cursor_encode(ordinal: int, evidence_id: str) -> str:
    return (
        base64.urlsafe_b64encode(_json({"o": ordinal, "id": evidence_id}).encode())
        .decode()
        .rstrip("=")
    )


def _cursor_decode(value: str | None) -> tuple[int, str] | None:
    if value is None:
        return None
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        data = json.loads(raw)
        ordinal = int(data["o"])
        evidence_id = str(data["id"])
        if ordinal < 1 or not evidence_id:
            raise ValueError
        return ordinal, evidence_id
    except (ValueError, KeyError, TypeError, UnicodeError, json.JSONDecodeError):
        raise AppError("VALIDATION_ERROR", "cursor 无效", 422) from None


def list_evidence(
    session: Session, user: User, source_id: str, *, limit: int, cursor: str | None
) -> EvidencePage:
    source = _owner_source(session, user, source_id)
    marker = _cursor_decode(cursor)
    statement = select(Evidence).where(Evidence.source_id == source.id)
    if marker is not None:
        ordinal, evidence_id = marker
        statement = statement.where(
            (Evidence.ordinal > ordinal)
            | ((Evidence.ordinal == ordinal) & (Evidence.id > evidence_id))
        )
    rows = session.exec(statement.order_by(Evidence.ordinal, Evidence.id).limit(limit + 1)).all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = _cursor_encode(rows[-1].ordinal, rows[-1].id) if has_next and rows else None
    return EvidencePage(items=[evidence_view(row, source) for row in rows], next_cursor=next_cursor)


def get_evidence(session: Session, user: User, evidence_id: str) -> EvidenceView:
    evidence = accessible_evidence(session, user, evidence_id)
    source = session.get(Source, evidence.source_id)
    if source is None:  # pragma: no cover - protected by foreign key
        raise AppError("NOT_FOUND", "资源不存在", 404)
    return evidence_view(evidence, source)


def storage_path(settings: Settings, source: Source) -> Path:
    root = (settings.data_dir / "uploads").resolve()
    path = (root / source.storage_key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise AppError("FILE_MISSING", "原文件不可用", 404)
    return path


def file_media_type(source: Source) -> str:
    return "application/pdf" if source.file_type == "pdf" else "text/plain; charset=utf-8"


def safe_download_name(source: Source) -> str:
    return _SAFE_FILE_RE.sub("_", source.file_name)[:200] or f"source.{source.file_type}"


def text_lines(
    session: Session, user: User, source_id: str, settings: Settings, *, start_line: int, limit: int
) -> TextLinesView:
    source = accessible_source(session, user, source_id)
    if source.file_type != "txt":
        raise AppError("VALIDATION_ERROR", "该资料不是 TXT", 422)
    if source.status != "ready":
        raise AppError("SOURCE_NOT_READY", "资料尚未解析完成", 409)
    path = storage_path(settings, source)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:  # immutable files were previously validated
        raise AppError("TEXT_DECODE_FAILED", "TXT 文件无法读取", 422) from exc
    return TextLinesView(
        source_id=source.id,
        total_lines=len(lines),
        start_line=start_line,
        lines=lines[start_line - 1 : start_line - 1 + limit],
    )


def _tokens(value: str) -> list[str]:
    return [token.strip().lower() for token in jieba.lcut_for_search(value) if token.strip()]


def search_evidence(
    session: Session, user: User, version_id: str, query: str, top_k: int
) -> EvidenceSearchResult:
    version = _owner_version(session, user, version_id)
    rows = session.exec(
        select(Evidence, Source)
        .join(Source, Source.id == Evidence.source_id)
        .join(VersionSource, VersionSource.source_id == Source.id)
        .where(VersionSource.version_id == version.id, Source.status == "ready")
        .order_by(Source.id, Evidence.ordinal)
    ).all()
    if not rows:
        return EvidenceSearchResult(evidence=[], insufficient_evidence=True)
    corpus = [_tokens(evidence.text) for evidence, _ in rows]
    query_tokens = _tokens(query)
    if not query_tokens:
        return EvidenceSearchResult(evidence=[], insufficient_evidence=True)
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
    selected = [
        rows[index]
        for index, score in ranked[:top_k]
        if float(score) > 0 or query_set.intersection(corpus[index])
    ]
    return EvidenceSearchResult(
        evidence=[evidence_view(evidence, source) for evidence, source in selected],
        insufficient_evidence=not selected,
    )


def get_run(session: Session, user: User, run_id: str) -> RunView:
    run = session.get(AgentRun, run_id)
    if run is None:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    task = session.get(Task, run.task_id)
    if task is None or user.role != "teacher" or task.owner_id != user.id:
        raise AppError("NOT_FOUND", "资源不存在", 404)
    return run_view(run)


def fail_interrupted_runs(engine: Any) -> int:
    with Session(engine) as session:
        rows = session.exec(
            select(AgentRun).where(AgentRun.kind == "parse_material", AgentRun.status == "running")
        ).all()
        now = _now()
        for run in rows:
            error = {
                "code": "PROCESS_INTERRUPTED",
                "message": "服务重启中断了资料解析",
                "retryable": True,
            }
            run.status = "failed"
            run.terminal_reason = "PROCESS_INTERRUPTED"
            run.error_json = _json(error)
            run.finished_at = now
            if run.source_id:
                source = session.get(Source, run.source_id)
                if source is not None:
                    source.status = "failed"
                    source.parse_error_json = _json(error)
                    source.updated_at = now
            max_seq = (
                session.exec(select(func.max(RunEvent.seq)).where(RunEvent.run_id == run.id)).one()
                or 0
            )
            session.add(
                _new_event(
                    run,
                    max_seq + 1,
                    "run.failed",
                    {"runId": run.id, "seq": max_seq + 1, "error": error},
                    now,
                )
            )
        session.commit()
        return len(rows)
