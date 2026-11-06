"""Persistent SQLModel rows (v1.1 contract).

JSON and fixed-format UTC timestamps intentionally remain TEXT. These are not
API schemas: services own UUID/time generation, JSON shapes, permissions and
immutability. No relationship cascades or implicit commits are configured.
"""

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        sa.UniqueConstraint("username"),
        sa.CheckConstraint("role IN ('teacher','student')", name="ck_users_1"),
        sa.CheckConstraint("is_active IN (0,1)", name="ck_users_2"),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    username: str = Field(sa_column=sa.Column("username", sa.Text(), nullable=False))
    display_name: str = Field(sa_column=sa.Column("display_name", sa.Text(), nullable=False))
    role: str = Field(sa_column=sa.Column("role", sa.Text(), nullable=False))
    password_hash: str = Field(sa_column=sa.Column("password_hash", sa.Text(), nullable=False))
    is_active: int = Field(
        default=1,
        sa_column=sa.Column("is_active", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))
    updated_at: str = Field(sa_column=sa.Column("updated_at", sa.Text(), nullable=False))


class LoginSession(SQLModel, table=True):
    __tablename__ = "login_sessions"
    __table_args__ = (
        sa.UniqueConstraint("token_hash"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.CheckConstraint("expires_at > created_at", name="ck_login_sessions_1"),
        sa.Index("ix_login_user_expiry", "user_id", "expires_at", unique=False),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    user_id: str = Field(sa_column=sa.Column("user_id", sa.Text(), nullable=False))
    token_hash: str = Field(sa_column=sa.Column("token_hash", sa.Text(), nullable=False))
    csrf_token: str = Field(sa_column=sa.Column("csrf_token", sa.Text(), nullable=False))
    expires_at: str = Field(sa_column=sa.Column("expires_at", sa.Text(), nullable=False))
    revoked_at: str | None = Field(
        default=None, sa_column=sa.Column("revoked_at", sa.Text(), nullable=True)
    )
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))


class Task(SQLModel, table=True):
    __tablename__ = "tasks"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["id", "current_published_version_id"],
            ["task_versions.task_id", "task_versions.id"],
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_tasks_1"),
        sa.CheckConstraint("row_version > 0", name="ck_tasks_2"),
        sa.CheckConstraint(
            "(status = 'active' AND archived_at IS NULL) OR (status = 'archived' AND "
            "archived_at IS NOT NULL)",
            name="ck_tasks_3",
        ),
        sa.Index("ix_tasks_owner_list", "owner_id", "status", "created_at", "id", unique=False),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    owner_id: str = Field(sa_column=sa.Column("owner_id", sa.Text(), nullable=False))
    status: str = Field(
        default="active",
        sa_column=sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'active'")
        ),
    )
    row_version: int = Field(
        default=1,
        sa_column=sa.Column(
            "row_version", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
    )
    current_published_version_id: str | None = Field(
        default=None, sa_column=sa.Column("current_published_version_id", sa.Text(), nullable=True)
    )
    archived_at: str | None = Field(
        default=None, sa_column=sa.Column("archived_at", sa.Text(), nullable=True)
    )
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))
    updated_at: str = Field(sa_column=sa.Column("updated_at", sa.Text(), nullable=False))


class TaskMember(SQLModel, table=True):
    __tablename__ = "task_members"
    __table_args__ = (
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.Index("ix_members_user", "user_id", "task_id", unique=False),
    )

    task_id: str = Field(
        sa_column=sa.Column("task_id", sa.Text(), nullable=False, primary_key=True)
    )
    user_id: str = Field(
        sa_column=sa.Column("user_id", sa.Text(), nullable=False, primary_key=True)
    )
    granted_by: str = Field(sa_column=sa.Column("granted_by", sa.Text(), nullable=False))
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))


class TaskVersion(SQLModel, table=True):
    __tablename__ = "task_versions"
    __table_args__ = (
        sa.UniqueConstraint("task_id", "version_no"),
        sa.UniqueConstraint("task_id", "id"),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["from_version_id"], ["task_versions.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.CheckConstraint("version_no > 0", name="ck_task_versions_1"),
        sa.CheckConstraint("revision > 0", name="ck_task_versions_2"),
        sa.CheckConstraint("status IN ('draft','published')", name="ck_task_versions_3"),
        sa.CheckConstraint(
            "json_valid(manual_fields_json) AND json_type(manual_fields_json) = 'array'",
            name="ck_task_versions_4",
        ),
        sa.CheckConstraint(
            "json_valid(generation_meta_json) AND json_type(generation_meta_json) = 'object'",
            name="ck_task_versions_5",
        ),
        sa.CheckConstraint("json_valid(brief_json)", name="ck_task_versions_6"),
        sa.CheckConstraint("json_valid(question_plan_json)", name="ck_task_versions_7"),
        sa.CheckConstraint(
            "validation_status IN ('stale','valid','invalid')", name="ck_task_versions_8"
        ),
        sa.CheckConstraint(
            "(validation_status = 'valid' AND validated_revision IS NOT NULL AND "
            "validated_revision = revision) OR (validation_status IN "
            "('stale','invalid') AND validated_revision IS NULL)",
            name="ck_task_versions_9",
        ),
        sa.CheckConstraint(
            "preview_revision IS NULL OR preview_revision = revision", name="ck_task_versions_10"
        ),
        sa.CheckConstraint(
            "(status = 'draft' AND published_at IS NULL AND published_by IS NULL AND "
            "content_hash IS NULL) OR (status = 'published' AND published_at IS NOT "
            "NULL AND published_by IS NOT NULL AND content_hash IS NOT NULL AND "
            "validation_status = 'valid' AND preview_revision IS NOT NULL AND "
            "preview_revision = revision)",
            name="ck_task_versions_11",
        ),
        sa.Index(
            "uq_one_draft_per_task",
            "task_id",
            unique=True,
            sqlite_where=sa.text("status = 'draft'"),
        ),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    task_id: str = Field(sa_column=sa.Column("task_id", sa.Text(), nullable=False))
    version_no: int = Field(sa_column=sa.Column("version_no", sa.Integer(), nullable=False))
    revision: int = Field(
        default=1,
        sa_column=sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    status: str = Field(
        default="draft",
        sa_column=sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
    )
    from_version_id: str | None = Field(
        default=None, sa_column=sa.Column("from_version_id", sa.Text(), nullable=True)
    )
    teaching_intent: str = Field(
        default="",
        sa_column=sa.Column(
            "teaching_intent", sa.Text(), nullable=False, server_default=sa.text("''")
        ),
    )
    manual_fields_json: str = Field(
        default="[]",
        sa_column=sa.Column(
            "manual_fields_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")
        ),
    )
    generation_meta_json: str = Field(
        default="{}",
        sa_column=sa.Column(
            "generation_meta_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")
        ),
    )
    brief_json: str = Field(
        default="{}",
        sa_column=sa.Column(
            "brief_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")
        ),
    )
    question_plan_json: str = Field(
        default="[]",
        sa_column=sa.Column(
            "question_plan_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")
        ),
    )
    validation_status: str = Field(
        default="stale",
        sa_column=sa.Column(
            "validation_status", sa.Text(), nullable=False, server_default=sa.text("'stale'")
        ),
    )
    validated_revision: int | None = Field(
        default=None, sa_column=sa.Column("validated_revision", sa.Integer(), nullable=True)
    )
    preview_revision: int | None = Field(
        default=None, sa_column=sa.Column("preview_revision", sa.Integer(), nullable=True)
    )
    content_hash: str | None = Field(
        default=None, sa_column=sa.Column("content_hash", sa.Text(), nullable=True)
    )
    published_at: str | None = Field(
        default=None, sa_column=sa.Column("published_at", sa.Text(), nullable=True)
    )
    published_by: str | None = Field(
        default=None, sa_column=sa.Column("published_by", sa.Text(), nullable=True)
    )
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))
    updated_at: str = Field(sa_column=sa.Column("updated_at", sa.Text(), nullable=False))


class RoleCard(SQLModel, table=True):
    __tablename__ = "role_cards"
    __table_args__ = (
        sa.UniqueConstraint("version_id"),
        sa.ForeignKeyConstraint(["edited_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["task_versions.id"]),
        sa.CheckConstraint("json_valid(card_json)", name="ck_role_cards_1"),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    version_id: str = Field(sa_column=sa.Column("version_id", sa.Text(), nullable=False))
    card_json: str = Field(sa_column=sa.Column("card_json", sa.Text(), nullable=False))
    edited_by: str = Field(sa_column=sa.Column("edited_by", sa.Text(), nullable=False))
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))
    updated_at: str = Field(sa_column=sa.Column("updated_at", sa.Text(), nullable=False))


class Source(SQLModel, table=True):
    __tablename__ = "sources"
    __table_args__ = (
        sa.UniqueConstraint("task_id", "id"),
        sa.UniqueConstraint("storage_key"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.CheckConstraint("file_type IN ('pdf','txt')", name="ck_sources_1"),
        sa.CheckConstraint("byte_size > 0", name="ck_sources_2"),
        sa.CheckConstraint("length(sha256) = 64", name="ck_sources_3"),
        sa.CheckConstraint(
            "status IN ('uploaded','parsing','ready','failed')", name="ck_sources_4"
        ),
        sa.CheckConstraint("page_count IS NULL OR page_count > 0", name="ck_sources_5"),
        sa.CheckConstraint("total_lines IS NULL OR total_lines > 0", name="ck_sources_6"),
        sa.CheckConstraint(
            "parse_error_json IS NULL OR json_valid(parse_error_json)", name="ck_sources_7"
        ),
        sa.CheckConstraint("json_valid(warnings_json)", name="ck_sources_8"),
        sa.CheckConstraint(
            "(status = 'failed' AND parse_error_json IS NOT NULL) OR (status <> "
            "'failed' AND parse_error_json IS NULL)",
            name="ck_sources_9",
        ),
        sa.CheckConstraint(
            "status <> 'ready' OR (parser_version IS NOT NULL AND ((file_type = 'pdf' "
            "AND page_count IS NOT NULL) OR (file_type = 'txt' AND total_lines IS NOT "
            "NULL)))",
            name="ck_sources_10",
        ),
        sa.Index("ix_sources_task_list", "task_id", "created_at", "id", unique=False),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    task_id: str = Field(sa_column=sa.Column("task_id", sa.Text(), nullable=False))
    uploaded_by: str = Field(sa_column=sa.Column("uploaded_by", sa.Text(), nullable=False))
    file_name: str = Field(sa_column=sa.Column("file_name", sa.Text(), nullable=False))
    file_type: str = Field(sa_column=sa.Column("file_type", sa.Text(), nullable=False))
    byte_size: int = Field(sa_column=sa.Column("byte_size", sa.Integer(), nullable=False))
    sha256: str = Field(sa_column=sa.Column("sha256", sa.Text(), nullable=False))
    storage_key: str = Field(sa_column=sa.Column("storage_key", sa.Text(), nullable=False))
    status: str = Field(
        default="uploaded",
        sa_column=sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'uploaded'")
        ),
    )
    page_count: int | None = Field(
        default=None, sa_column=sa.Column("page_count", sa.Integer(), nullable=True)
    )
    total_lines: int | None = Field(
        default=None, sa_column=sa.Column("total_lines", sa.Integer(), nullable=True)
    )
    parser_version: str | None = Field(
        default=None, sa_column=sa.Column("parser_version", sa.Text(), nullable=True)
    )
    parse_error_json: str | None = Field(
        default=None, sa_column=sa.Column("parse_error_json", sa.Text(), nullable=True)
    )
    warnings_json: str = Field(
        default="[]",
        sa_column=sa.Column(
            "warnings_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")
        ),
    )
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))
    updated_at: str = Field(sa_column=sa.Column("updated_at", sa.Text(), nullable=False))


class VersionSource(SQLModel, table=True):
    __tablename__ = "version_sources"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["task_id", "version_id"], ["task_versions.task_id", "task_versions.id"]
        ),
        sa.ForeignKeyConstraint(["task_id", "source_id"], ["sources.task_id", "sources.id"]),
        sa.Index("ix_version_sources_source", "source_id", unique=False),
    )

    task_id: str = Field(sa_column=sa.Column("task_id", sa.Text(), nullable=False))
    version_id: str = Field(
        sa_column=sa.Column("version_id", sa.Text(), nullable=False, primary_key=True)
    )
    source_id: str = Field(
        sa_column=sa.Column("source_id", sa.Text(), nullable=False, primary_key=True)
    )
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))


class Evidence(SQLModel, table=True):
    __tablename__ = "evidence"
    __table_args__ = (
        sa.UniqueConstraint("source_id", "ordinal"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.CheckConstraint("ordinal > 0", name="ck_evidence_1"),
        sa.CheckConstraint("length(trim(text)) > 0", name="ck_evidence_2"),
        sa.CheckConstraint("page_no IS NULL OR page_no > 0", name="ck_evidence_3"),
        sa.CheckConstraint("paragraph_no > 0", name="ck_evidence_4"),
        sa.CheckConstraint("disputed IN (0,1)", name="ck_evidence_5"),
        sa.CheckConstraint(
            "(page_no IS NOT NULL AND start_line IS NULL AND end_line IS NULL) OR "
            "(page_no IS NULL AND start_line IS NOT NULL AND end_line IS NOT NULL AND "
            "start_line > 0 AND end_line >= start_line)",
            name="ck_evidence_6",
        ),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    source_id: str = Field(sa_column=sa.Column("source_id", sa.Text(), nullable=False))
    ordinal: int = Field(sa_column=sa.Column("ordinal", sa.Integer(), nullable=False))
    text: str = Field(sa_column=sa.Column("text", sa.Text(), nullable=False))
    page_no: int | None = Field(
        default=None, sa_column=sa.Column("page_no", sa.Integer(), nullable=True)
    )
    paragraph_no: int = Field(sa_column=sa.Column("paragraph_no", sa.Integer(), nullable=False))
    start_line: int | None = Field(
        default=None, sa_column=sa.Column("start_line", sa.Integer(), nullable=True)
    )
    end_line: int | None = Field(
        default=None, sa_column=sa.Column("end_line", sa.Integer(), nullable=True)
    )
    disputed: int = Field(
        default=0,
        sa_column=sa.Column("disputed", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))


class RoleSession(SQLModel, table=True):
    __tablename__ = "role_sessions"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["task_id", "version_id"], ["task_versions.task_id", "task_versions.id"]
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.CheckConstraint("version_revision > 0", name="ck_role_sessions_1"),
        sa.CheckConstraint("mode IN ('preview','student')", name="ck_role_sessions_2"),
        sa.CheckConstraint("status IN ('active','ended')", name="ck_role_sessions_3"),
        sa.CheckConstraint("json_valid(snapshot_json)", name="ck_role_sessions_4"),
        sa.CheckConstraint("json_valid(summary_json)", name="ck_role_sessions_5"),
        sa.CheckConstraint("summary_through_seq >= 0", name="ck_role_sessions_6"),
        sa.CheckConstraint("completed_turns >= 0", name="ck_role_sessions_7"),
        sa.CheckConstraint("learning_revision >= 0", name="ck_role_sessions_8"),
        sa.CheckConstraint(
            "(status = 'active' AND ended_at IS NULL) OR (status = 'ended' AND "
            "ended_at IS NOT NULL)",
            name="ck_role_sessions_9",
        ),
        sa.Index("ix_sessions_task_list", "task_id", "mode", "created_at", "id", unique=False),
        sa.Index("ix_sessions_version", "version_id", unique=False),
        sa.Index(
            "uq_student_session",
            "owner_id",
            "version_id",
            unique=True,
            sqlite_where=sa.text("mode = 'student'"),
        ),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    task_id: str = Field(sa_column=sa.Column("task_id", sa.Text(), nullable=False))
    version_id: str = Field(sa_column=sa.Column("version_id", sa.Text(), nullable=False))
    version_revision: int = Field(
        sa_column=sa.Column("version_revision", sa.Integer(), nullable=False)
    )
    owner_id: str = Field(sa_column=sa.Column("owner_id", sa.Text(), nullable=False))
    mode: str = Field(sa_column=sa.Column("mode", sa.Text(), nullable=False))
    status: str = Field(
        default="active",
        sa_column=sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'active'")
        ),
    )
    snapshot_json: str = Field(sa_column=sa.Column("snapshot_json", sa.Text(), nullable=False))
    summary_json: str = Field(
        default="{}",
        sa_column=sa.Column(
            "summary_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")
        ),
    )
    summary_through_seq: int = Field(
        default=0,
        sa_column=sa.Column(
            "summary_through_seq", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    completed_turns: int = Field(
        default=0,
        sa_column=sa.Column(
            "completed_turns", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    learning_revision: int = Field(
        default=0,
        sa_column=sa.Column(
            "learning_revision", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    event_tracking_started_at: str | None = Field(
        default=None, sa_column=sa.Column("event_tracking_started_at", sa.Text(), nullable=True)
    )
    ended_at: str | None = Field(
        default=None, sa_column=sa.Column("ended_at", sa.Text(), nullable=True)
    )
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))
    updated_at: str = Field(sa_column=sa.Column("updated_at", sa.Text(), nullable=False))


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    __table_args__ = (
        sa.UniqueConstraint("session_id", "seq"),
        sa.UniqueConstraint("id", "session_id"),
        sa.UniqueConstraint("run_id"),
        sa.ForeignKeyConstraint(
            ["run_id", "session_id"], ["agent_runs.id", "agent_runs.session_id"]
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_message_id", "session_id"], ["messages.id", "messages.session_id"]
        ),
        sa.ForeignKeyConstraint(["session_id"], ["role_sessions.id"]),
        sa.CheckConstraint("seq > 0", name="ck_messages_1"),
        sa.CheckConstraint("speaker IN ('user','assistant')", name="ck_messages_2"),
        sa.CheckConstraint(
            "status IN ('pending','partial','complete','discarded')", name="ck_messages_3"
        ),
        sa.CheckConstraint("json_valid(blocks_json)", name="ck_messages_4"),
        sa.CheckConstraint("json_valid(meta_json)", name="ck_messages_5"),
        sa.CheckConstraint(
            "(speaker = 'user' AND run_id IS NULL AND status = 'complete' AND "
            "supersedes_message_id IS NULL) OR (speaker = 'assistant' AND run_id IS "
            "NOT NULL)",
            name="ck_messages_6",
        ),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    session_id: str = Field(sa_column=sa.Column("session_id", sa.Text(), nullable=False))
    seq: int = Field(sa_column=sa.Column("seq", sa.Integer(), nullable=False))
    speaker: str = Field(sa_column=sa.Column("speaker", sa.Text(), nullable=False))
    status: str = Field(sa_column=sa.Column("status", sa.Text(), nullable=False))
    text: str = Field(
        default="",
        sa_column=sa.Column("text", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    blocks_json: str = Field(
        default="[]",
        sa_column=sa.Column(
            "blocks_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")
        ),
    )
    meta_json: str = Field(
        default="{}",
        sa_column=sa.Column("meta_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
    )
    run_id: str | None = Field(
        default=None, sa_column=sa.Column("run_id", sa.Text(), nullable=True)
    )
    supersedes_message_id: str | None = Field(
        default=None, sa_column=sa.Column("supersedes_message_id", sa.Text(), nullable=True)
    )
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))
    updated_at: str = Field(sa_column=sa.Column("updated_at", sa.Text(), nullable=False))


class Citation(SQLModel, table=True):
    __tablename__ = "citations"
    __table_args__ = (
        sa.UniqueConstraint("message_id", "block_index", "evidence_id"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"]),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.CheckConstraint("block_index >= 0", name="ck_citations_1"),
        sa.CheckConstraint("length(trim(quote)) > 0", name="ck_citations_2"),
        sa.Index("ix_citations_evidence", "evidence_id", unique=False),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    message_id: str = Field(sa_column=sa.Column("message_id", sa.Text(), nullable=False))
    block_index: int = Field(sa_column=sa.Column("block_index", sa.Integer(), nullable=False))
    evidence_id: str = Field(sa_column=sa.Column("evidence_id", sa.Text(), nullable=False))
    quote: str = Field(sa_column=sa.Column("quote", sa.Text(), nullable=False))
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))


class ExplorationNote(SQLModel, table=True):
    __tablename__ = "exploration_notes"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["message_id", "session_id"], ["messages.id", "messages.session_id"]
        ),
        sa.ForeignKeyConstraint(["session_id"], ["role_sessions.id"]),
        sa.CheckConstraint("block_index >= 0", name="ck_exploration_notes_1"),
        sa.CheckConstraint(
            "answer_type IN ('fact','opinion','inference','unknown')", name="ck_exploration_notes_2"
        ),
        sa.CheckConstraint("json_valid(evidence_ids_json)", name="ck_exploration_notes_3"),
        sa.CheckConstraint(
            "credibility IN ('unassessed','high','medium','low')", name="ck_exploration_notes_4"
        ),
        sa.CheckConstraint("row_version > 0", name="ck_exploration_notes_5"),
        sa.Index(
            "ix_notes_session_list",
            "session_id",
            "created_at",
            "id",
            unique=False,
            sqlite_where=sa.text("deleted_at IS NULL"),
        ),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    session_id: str = Field(sa_column=sa.Column("session_id", sa.Text(), nullable=False))
    message_id: str = Field(sa_column=sa.Column("message_id", sa.Text(), nullable=False))
    block_index: int = Field(sa_column=sa.Column("block_index", sa.Integer(), nullable=False))
    original_view: str = Field(sa_column=sa.Column("original_view", sa.Text(), nullable=False))
    answer_type: str = Field(sa_column=sa.Column("answer_type", sa.Text(), nullable=False))
    evidence_ids_json: str = Field(
        default="[]",
        sa_column=sa.Column(
            "evidence_ids_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")
        ),
    )
    judgment: str = Field(
        default="",
        sa_column=sa.Column("judgment", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    credibility: str = Field(
        default="unassessed",
        sa_column=sa.Column(
            "credibility", sa.Text(), nullable=False, server_default=sa.text("'unassessed'")
        ),
    )
    limitations: str = Field(
        default="",
        sa_column=sa.Column("limitations", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    row_version: int = Field(
        default=1,
        sa_column=sa.Column(
            "row_version", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
    )
    deleted_at: str | None = Field(
        default=None, sa_column=sa.Column("deleted_at", sa.Text(), nullable=True)
    )
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))
    updated_at: str = Field(sa_column=sa.Column("updated_at", sa.Text(), nullable=False))


class Submission(SQLModel, table=True):
    __tablename__ = "submissions"
    __table_args__ = (
        sa.UniqueConstraint("session_id"),
        sa.ForeignKeyConstraint(["session_id"], ["role_sessions.id"]),
        sa.CheckConstraint("status IN ('draft','submitted')", name="ck_submissions_1"),
        sa.CheckConstraint("json_valid(content_json)", name="ck_submissions_2"),
        sa.CheckConstraint("row_version > 0", name="ck_submissions_3"),
        sa.CheckConstraint(
            "(status = 'draft' AND submitted_at IS NULL) OR (status = 'submitted' AND "
            "submitted_at IS NOT NULL)",
            name="ck_submissions_4",
        ),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    session_id: str = Field(sa_column=sa.Column("session_id", sa.Text(), nullable=False))
    status: str = Field(
        default="draft",
        sa_column=sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
    )
    content_json: str = Field(
        default="{}",
        sa_column=sa.Column(
            "content_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")
        ),
    )
    row_version: int = Field(
        default=1,
        sa_column=sa.Column(
            "row_version", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
    )
    submitted_at: str | None = Field(
        default=None, sa_column=sa.Column("submitted_at", sa.Text(), nullable=True)
    )
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))
    updated_at: str = Field(sa_column=sa.Column("updated_at", sa.Text(), nullable=False))


class LearningEvent(SQLModel, table=True):
    __tablename__ = "learning_events"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["message_id", "session_id"], ["messages.id", "messages.session_id"]
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["role_sessions.id"]),
        sa.CheckConstraint("event_type IN ('source_open','stance')", name="ck_learning_events_1"),
        sa.CheckConstraint("row_version > 0", name="ck_learning_events_2"),
        sa.CheckConstraint(
            "(event_type = 'source_open' AND source_id IS NOT NULL AND message_id IS "
            "NULL AND value IS NULL) OR (event_type = 'stance' AND source_id IS NULL "
            "AND message_id IS NOT NULL AND value IS NOT NULL AND value IN "
            "('need_more_evidence','agree_for_now','alternative_explanation'))",
            name="ck_learning_events_3",
        ),
        sa.Index(
            "ix_learning_events_session", "session_id", "event_type", "updated_at", unique=False
        ),
        sa.Index(
            "uq_source_open_event",
            "session_id",
            "source_id",
            unique=True,
            sqlite_where=sa.text("event_type = 'source_open'"),
        ),
        sa.Index(
            "uq_stance_event",
            "session_id",
            "message_id",
            unique=True,
            sqlite_where=sa.text("event_type = 'stance'"),
        ),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    session_id: str = Field(sa_column=sa.Column("session_id", sa.Text(), nullable=False))
    event_type: str = Field(sa_column=sa.Column("event_type", sa.Text(), nullable=False))
    source_id: str | None = Field(
        default=None, sa_column=sa.Column("source_id", sa.Text(), nullable=True)
    )
    message_id: str | None = Field(
        default=None, sa_column=sa.Column("message_id", sa.Text(), nullable=True)
    )
    value: str | None = Field(default=None, sa_column=sa.Column("value", sa.Text(), nullable=True))
    row_version: int = Field(
        default=1,
        sa_column=sa.Column(
            "row_version", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
    )
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))
    updated_at: str = Field(sa_column=sa.Column("updated_at", sa.Text(), nullable=False))


class LearningReport(SQLModel, table=True):
    __tablename__ = "learning_reports"
    __table_args__ = (
        sa.UniqueConstraint("id", "session_id"),
        sa.UniqueConstraint("session_id", "report_no"),
        sa.UniqueConstraint("session_id", "kind", "input_revision"),
        sa.ForeignKeyConstraint(
            ["generation_run_id", "session_id"], ["agent_runs.id", "agent_runs.session_id"]
        ),
        sa.ForeignKeyConstraint(["session_id"], ["role_sessions.id"]),
        sa.CheckConstraint("report_no > 0", name="ck_learning_reports_1"),
        sa.CheckConstraint("kind IN ('live','final')", name="ck_learning_reports_2"),
        sa.CheckConstraint(
            "status IN ('queued','generating','ready','failed','superseded')",
            name="ck_learning_reports_3",
        ),
        sa.CheckConstraint("input_revision > 0", name="ck_learning_reports_4"),
        sa.CheckConstraint("length(input_hash) = 64", name="ck_learning_reports_5"),
        sa.CheckConstraint(
            "json_valid(input_snapshot_json) AND json_type(input_snapshot_json) = 'object'",
            name="ck_learning_reports_6",
        ),
        sa.CheckConstraint(
            "content_json IS NULL OR (json_valid(content_json) AND "
            "json_type(content_json) = 'object')",
            name="ck_learning_reports_7",
        ),
        sa.CheckConstraint(
            "error_json IS NULL OR json_valid(error_json)", name="ck_learning_reports_8"
        ),
        sa.CheckConstraint(
            "(status = 'ready' AND content_json IS NOT NULL AND generated_at IS NOT "
            "NULL) OR (status <> 'ready' AND content_json IS NULL AND generated_at IS "
            "NULL)",
            name="ck_learning_reports_9",
        ),
        sa.CheckConstraint(
            "(status = 'failed' AND error_json IS NOT NULL) OR (status <> 'failed' "
            "AND error_json IS NULL)",
            name="ck_learning_reports_10",
        ),
        sa.CheckConstraint(
            "(status IN ('queued','superseded') AND generation_run_id IS NULL) OR "
            "(status IN ('generating','ready','failed') AND generation_run_id IS NOT "
            "NULL)",
            name="ck_learning_reports_11",
        ),
        sa.Index(
            "ix_learning_reports_latest",
            "session_id",
            "kind",
            sa.text("input_revision DESC"),
            unique=False,
        ),
        sa.Index("ix_learning_reports_queue", "status", "created_at", "id", unique=False),
        sa.Index(
            "uq_final_learning_report",
            "session_id",
            unique=True,
            sqlite_where=sa.text("kind = 'final'"),
        ),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    session_id: str = Field(sa_column=sa.Column("session_id", sa.Text(), nullable=False))
    report_no: int = Field(sa_column=sa.Column("report_no", sa.Integer(), nullable=False))
    kind: str = Field(sa_column=sa.Column("kind", sa.Text(), nullable=False))
    status: str = Field(
        default="queued",
        sa_column=sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'queued'")
        ),
    )
    input_revision: int = Field(sa_column=sa.Column("input_revision", sa.Integer(), nullable=False))
    input_hash: str = Field(sa_column=sa.Column("input_hash", sa.Text(), nullable=False))
    input_snapshot_json: str = Field(
        sa_column=sa.Column("input_snapshot_json", sa.Text(), nullable=False)
    )
    generation_run_id: str | None = Field(
        default=None, sa_column=sa.Column("generation_run_id", sa.Text(), nullable=True)
    )
    content_json: str | None = Field(
        default=None, sa_column=sa.Column("content_json", sa.Text(), nullable=True)
    )
    error_json: str | None = Field(
        default=None, sa_column=sa.Column("error_json", sa.Text(), nullable=True)
    )
    generated_at: str | None = Field(
        default=None, sa_column=sa.Column("generated_at", sa.Text(), nullable=True)
    )
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))
    updated_at: str = Field(sa_column=sa.Column("updated_at", sa.Text(), nullable=False))


class ReportCorrection(SQLModel, table=True):
    __tablename__ = "report_corrections"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["report_id", "session_id"], ["learning_reports.id", "learning_reports.session_id"]
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["role_sessions.id"]),
        sa.CheckConstraint("length(trim(text)) BETWEEN 1 AND 2000", name="ck_report_corrections_1"),
        sa.Index("ix_report_corrections_session", "session_id", "created_at", "id", unique=False),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    session_id: str = Field(sa_column=sa.Column("session_id", sa.Text(), nullable=False))
    report_id: str = Field(sa_column=sa.Column("report_id", sa.Text(), nullable=False))
    author_id: str = Field(sa_column=sa.Column("author_id", sa.Text(), nullable=False))
    text: str = Field(sa_column=sa.Column("text", sa.Text(), nullable=False))
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))


class AgentRun(SQLModel, table=True):
    __tablename__ = "agent_runs"
    __table_args__ = (
        sa.UniqueConstraint("id", "session_id"),
        sa.ForeignKeyConstraint(
            ["task_id", "version_id"], ["task_versions.task_id", "task_versions.id"]
        ),
        sa.ForeignKeyConstraint(
            ["input_message_id", "session_id"], ["messages.id", "messages.session_id"]
        ),
        sa.ForeignKeyConstraint(
            ["output_message_id", "session_id"], ["messages.id", "messages.session_id"]
        ),
        sa.ForeignKeyConstraint(["retry_of_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["role_sessions.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.CheckConstraint("version_revision > 0", name="ck_agent_runs_1"),
        sa.CheckConstraint(
            "kind IN "
            "('parse_material','role_generate','role_validate','plan_generate','publis"
            "h_preflight','chat','summary','learning_report')",
            name="ck_agent_runs_2",
        ),
        sa.CheckConstraint(
            "status IN ('running','waiting_confirmation','completed','failed','cancelled')",
            name="ck_agent_runs_3",
        ),
        sa.CheckConstraint("step_count >= 0", name="ck_agent_runs_4"),
        sa.CheckConstraint("max_steps > 0", name="ck_agent_runs_5"),
        sa.CheckConstraint("json_valid(execution_config_json)", name="ck_agent_runs_6"),
        sa.CheckConstraint(
            "result_json IS NULL OR json_valid(result_json)", name="ck_agent_runs_7"
        ),
        sa.CheckConstraint("error_json IS NULL OR json_valid(error_json)", name="ck_agent_runs_8"),
        sa.CheckConstraint("step_count <= max_steps", name="ck_agent_runs_9"),
        sa.CheckConstraint("deadline_at > created_at", name="ck_agent_runs_10"),
        sa.CheckConstraint(
            "(kind IN ('chat','summary','learning_report') AND session_id IS NOT NULL "
            "AND source_id IS NULL) OR (kind = 'parse_material' AND source_id IS NOT "
            "NULL AND session_id IS NULL) OR (kind IN "
            "('role_generate','role_validate','plan_generate','publish_preflight') "
            "AND session_id IS NULL AND source_id IS NULL)",
            name="ck_agent_runs_11",
        ),
        sa.CheckConstraint(
            "(kind = 'chat' AND input_message_id IS NOT NULL) OR (kind <> 'chat' AND "
            "input_message_id IS NULL AND output_message_id IS NULL AND "
            "retry_of_run_id IS NULL)",
            name="ck_agent_runs_12",
        ),
        sa.CheckConstraint(
            "status <> 'waiting_confirmation' OR (kind = 'role_generate' AND "
            "result_json IS NOT NULL)",
            name="ck_agent_runs_13",
        ),
        sa.CheckConstraint(
            "(status IN ('running','waiting_confirmation') AND finished_at IS NULL) "
            "OR (status IN ('completed','failed','cancelled') AND finished_at IS NOT "
            "NULL)",
            name="ck_agent_runs_14",
        ),
        sa.Index("ix_runs_actor_status", "actor_id", "status", unique=False),
        sa.Index("ix_runs_task_list", "task_id", "created_at", "id", unique=False),
        sa.Index("ix_runs_version", "version_id", "version_revision", unique=False),
        sa.Index(
            "uq_completed_chat_question",
            "input_message_id",
            unique=True,
            sqlite_where=sa.text("kind = 'chat' AND status = 'completed'"),
        ),
        sa.Index(
            "uq_running_report",
            "session_id",
            unique=True,
            sqlite_where=sa.text("status = 'running' AND kind = 'learning_report'"),
        ),
        sa.Index(
            "uq_running_session",
            "session_id",
            unique=True,
            sqlite_where=sa.text("status = 'running' AND kind IN ('chat','summary')"),
        ),
        sa.Index(
            "uq_running_version_workflow",
            "version_id",
            "version_revision",
            "kind",
            unique=True,
            sqlite_where=sa.text(
                "status = 'running' AND kind IN "
                "('plan_generate','publish_preflight','role_validate')"
            ),
        ),
        sa.Index(
            "uq_source_parsing_run",
            "source_id",
            unique=True,
            sqlite_where=sa.text("kind = 'parse_material' AND status = 'running'"),
        ),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    actor_id: str = Field(sa_column=sa.Column("actor_id", sa.Text(), nullable=False))
    task_id: str = Field(sa_column=sa.Column("task_id", sa.Text(), nullable=False))
    version_id: str = Field(sa_column=sa.Column("version_id", sa.Text(), nullable=False))
    version_revision: int = Field(
        sa_column=sa.Column("version_revision", sa.Integer(), nullable=False)
    )
    kind: str = Field(sa_column=sa.Column("kind", sa.Text(), nullable=False))
    status: str = Field(
        default="running",
        sa_column=sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'running'")
        ),
    )
    session_id: str | None = Field(
        default=None, sa_column=sa.Column("session_id", sa.Text(), nullable=True)
    )
    source_id: str | None = Field(
        default=None, sa_column=sa.Column("source_id", sa.Text(), nullable=True)
    )
    input_message_id: str | None = Field(
        default=None, sa_column=sa.Column("input_message_id", sa.Text(), nullable=True)
    )
    output_message_id: str | None = Field(
        default=None, sa_column=sa.Column("output_message_id", sa.Text(), nullable=True)
    )
    retry_of_run_id: str | None = Field(
        default=None, sa_column=sa.Column("retry_of_run_id", sa.Text(), nullable=True)
    )
    step_count: int = Field(
        default=0,
        sa_column=sa.Column(
            "step_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    max_steps: int = Field(
        default=20,
        sa_column=sa.Column(
            "max_steps", sa.Integer(), nullable=False, server_default=sa.text("20")
        ),
    )
    deadline_at: str = Field(sa_column=sa.Column("deadline_at", sa.Text(), nullable=False))
    cancel_requested_at: str | None = Field(
        default=None, sa_column=sa.Column("cancel_requested_at", sa.Text(), nullable=True)
    )
    terminal_reason: str | None = Field(
        default=None, sa_column=sa.Column("terminal_reason", sa.Text(), nullable=True)
    )
    execution_config_json: str = Field(
        default="{}",
        sa_column=sa.Column(
            "execution_config_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")
        ),
    )
    result_json: str | None = Field(
        default=None, sa_column=sa.Column("result_json", sa.Text(), nullable=True)
    )
    error_json: str | None = Field(
        default=None, sa_column=sa.Column("error_json", sa.Text(), nullable=True)
    )
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))
    finished_at: str | None = Field(
        default=None, sa_column=sa.Column("finished_at", sa.Text(), nullable=True)
    )


class RunStep(SQLModel, table=True):
    __tablename__ = "run_steps"
    __table_args__ = (
        sa.UniqueConstraint("run_id", "step_no", "attempt"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.CheckConstraint("step_no > 0", name="ck_run_steps_1"),
        sa.CheckConstraint("attempt BETWEEN 1 AND 3", name="ck_run_steps_2"),
        sa.CheckConstraint(
            "status IN ('running','completed','failed','cancelled')", name="ck_run_steps_3"
        ),
        sa.CheckConstraint("json_valid(input_summary_json)", name="ck_run_steps_4"),
        sa.CheckConstraint(
            "output_summary_json IS NULL OR json_valid(output_summary_json)", name="ck_run_steps_5"
        ),
        sa.CheckConstraint("error_json IS NULL OR json_valid(error_json)", name="ck_run_steps_6"),
        sa.CheckConstraint(
            "(status = 'running' AND finished_at IS NULL) OR (status <> 'running' AND "
            "finished_at IS NOT NULL)",
            name="ck_run_steps_7",
        ),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    run_id: str = Field(sa_column=sa.Column("run_id", sa.Text(), nullable=False))
    step_no: int = Field(sa_column=sa.Column("step_no", sa.Integer(), nullable=False))
    attempt: int = Field(sa_column=sa.Column("attempt", sa.Integer(), nullable=False))
    name: str = Field(sa_column=sa.Column("name", sa.Text(), nullable=False))
    status: str = Field(sa_column=sa.Column("status", sa.Text(), nullable=False))
    input_summary_json: str = Field(
        default="{}",
        sa_column=sa.Column(
            "input_summary_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")
        ),
    )
    output_summary_json: str | None = Field(
        default=None, sa_column=sa.Column("output_summary_json", sa.Text(), nullable=True)
    )
    error_json: str | None = Field(
        default=None, sa_column=sa.Column("error_json", sa.Text(), nullable=True)
    )
    started_at: str = Field(sa_column=sa.Column("started_at", sa.Text(), nullable=False))
    finished_at: str | None = Field(
        default=None, sa_column=sa.Column("finished_at", sa.Text(), nullable=True)
    )


class RunEvent(SQLModel, table=True):
    __tablename__ = "run_events"
    __table_args__ = (
        sa.UniqueConstraint("run_id", "seq"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.CheckConstraint("seq > 0", name="ck_run_events_1"),
        sa.CheckConstraint(
            "event_type IN "
            "('run.started','run.progress','answer.block','answer.meta','run.waiting_c"
            "onfirmation', 'run.completed','run.failed','run.cancelled')",
            name="ck_run_events_2",
        ),
        sa.CheckConstraint("json_valid(payload_json)", name="ck_run_events_3"),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    run_id: str = Field(sa_column=sa.Column("run_id", sa.Text(), nullable=False))
    seq: int = Field(sa_column=sa.Column("seq", sa.Integer(), nullable=False))
    event_type: str = Field(sa_column=sa.Column("event_type", sa.Text(), nullable=False))
    payload_json: str = Field(sa_column=sa.Column("payload_json", sa.Text(), nullable=False))
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))


class ReviewRecord(SQLModel, table=True):
    __tablename__ = "review_records"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["task_id", "version_id"], ["task_versions.task_id", "task_versions.id"]
        ),
        sa.ForeignKeyConstraint(
            ["message_id", "session_id"], ["messages.id", "messages.session_id"]
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["role_sessions.id"]),
        sa.CheckConstraint("version_revision > 0", name="ck_review_records_1"),
        sa.CheckConstraint(
            "kind IN "
            "('role_validation','answer_check','preview_review','publish_preflight','e"
            "valuation','business_audit')",
            name="ck_review_records_2",
        ),
        sa.CheckConstraint("block_index IS NULL OR block_index >= 0", name="ck_review_records_3"),
        sa.CheckConstraint("passed IS NULL OR passed IN (0,1)", name="ck_review_records_4"),
        sa.CheckConstraint("json_valid(result_json)", name="ck_review_records_5"),
        sa.CheckConstraint("json_valid(issues_json)", name="ck_review_records_6"),
        sa.CheckConstraint(
            "message_id IS NULL OR session_id IS NOT NULL", name="ck_review_records_7"
        ),
        sa.CheckConstraint(
            "block_index IS NULL OR message_id IS NOT NULL", name="ck_review_records_8"
        ),
        sa.Index("ix_reviews_session_list", "session_id", "created_at", "id", unique=False),
        sa.Index("ix_reviews_version_kind", "version_id", "version_revision", "kind", unique=False),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    task_id: str = Field(sa_column=sa.Column("task_id", sa.Text(), nullable=False))
    version_id: str = Field(sa_column=sa.Column("version_id", sa.Text(), nullable=False))
    version_revision: int = Field(
        sa_column=sa.Column("version_revision", sa.Integer(), nullable=False)
    )
    kind: str = Field(sa_column=sa.Column("kind", sa.Text(), nullable=False))
    session_id: str | None = Field(
        default=None, sa_column=sa.Column("session_id", sa.Text(), nullable=True)
    )
    run_id: str | None = Field(
        default=None, sa_column=sa.Column("run_id", sa.Text(), nullable=True)
    )
    message_id: str | None = Field(
        default=None, sa_column=sa.Column("message_id", sa.Text(), nullable=True)
    )
    block_index: int | None = Field(
        default=None, sa_column=sa.Column("block_index", sa.Integer(), nullable=True)
    )
    actor_id: str | None = Field(
        default=None, sa_column=sa.Column("actor_id", sa.Text(), nullable=True)
    )
    passed: int | None = Field(
        default=None, sa_column=sa.Column("passed", sa.Integer(), nullable=True)
    )
    result_json: str = Field(
        default="{}",
        sa_column=sa.Column(
            "result_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")
        ),
    )
    issues_json: str = Field(
        default="[]",
        sa_column=sa.Column(
            "issues_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")
        ),
    )
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))


class Confirmation(SQLModel, table=True):
    __tablename__ = "confirmations"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["task_id", "version_id"], ["task_versions.task_id", "task_versions.id"]
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.CheckConstraint("version_revision > 0", name="ck_confirmations_1"),
        sa.CheckConstraint("task_revision > 0", name="ck_confirmations_2"),
        sa.CheckConstraint(
            "action IN ('publish_version','apply_role_candidate','archive_task','replace_plan')",
            name="ck_confirmations_3",
        ),
        sa.CheckConstraint("json_valid(payload_json)", name="ck_confirmations_4"),
        sa.CheckConstraint("length(payload_hash) = 64", name="ck_confirmations_5"),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_confirmations_6"),
        sa.CheckConstraint("expires_at > created_at", name="ck_confirmations_7"),
        sa.CheckConstraint(
            "consumed_at IS NULL OR (consumed_at >= created_at AND consumed_at < expires_at)",
            name="ck_confirmations_8",
        ),
        sa.Index("ix_confirmations_expiry", "expires_at", unique=False),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    task_id: str = Field(sa_column=sa.Column("task_id", sa.Text(), nullable=False))
    version_id: str = Field(sa_column=sa.Column("version_id", sa.Text(), nullable=False))
    version_revision: int = Field(
        sa_column=sa.Column("version_revision", sa.Integer(), nullable=False)
    )
    task_revision: int = Field(sa_column=sa.Column("task_revision", sa.Integer(), nullable=False))
    actor_id: str = Field(sa_column=sa.Column("actor_id", sa.Text(), nullable=False))
    action: str = Field(sa_column=sa.Column("action", sa.Text(), nullable=False))
    payload_json: str = Field(sa_column=sa.Column("payload_json", sa.Text(), nullable=False))
    payload_hash: str = Field(sa_column=sa.Column("payload_hash", sa.Text(), nullable=False))
    content_hash: str = Field(sa_column=sa.Column("content_hash", sa.Text(), nullable=False))
    expires_at: str = Field(sa_column=sa.Column("expires_at", sa.Text(), nullable=False))
    consumed_at: str | None = Field(
        default=None, sa_column=sa.Column("consumed_at", sa.Text(), nullable=True)
    )
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))


class IdempotencyKey(SQLModel, table=True):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        sa.UniqueConstraint("user_id", "method", "path", "key"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.CheckConstraint("length(key) BETWEEN 1 AND 128", name="ck_idempotency_keys_1"),
        sa.CheckConstraint("length(request_hash) = 64", name="ck_idempotency_keys_2"),
        sa.CheckConstraint("status IN ('in_progress','completed')", name="ck_idempotency_keys_3"),
        sa.CheckConstraint(
            "response_status IS NULL OR response_status BETWEEN 200 AND 599",
            name="ck_idempotency_keys_4",
        ),
        sa.CheckConstraint(
            "response_json IS NULL OR json_valid(response_json)", name="ck_idempotency_keys_5"
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_idempotency_keys_6"),
        sa.CheckConstraint(
            "(status = 'in_progress' AND response_status IS NULL AND response_json IS "
            "NULL) OR (status = 'completed' AND response_status IS NOT NULL AND "
            "response_json IS NOT NULL)",
            name="ck_idempotency_keys_7",
        ),
        sa.Index("ix_idempotency_expiry", "expires_at", unique=False),
    )

    id: str = Field(sa_column=sa.Column("id", sa.Text(), nullable=False, primary_key=True))
    user_id: str = Field(sa_column=sa.Column("user_id", sa.Text(), nullable=False))
    method: str = Field(sa_column=sa.Column("method", sa.Text(), nullable=False))
    path: str = Field(sa_column=sa.Column("path", sa.Text(), nullable=False))
    key: str = Field(sa_column=sa.Column("key", sa.Text(), nullable=False))
    request_hash: str = Field(sa_column=sa.Column("request_hash", sa.Text(), nullable=False))
    status: str = Field(sa_column=sa.Column("status", sa.Text(), nullable=False))
    response_status: int | None = Field(
        default=None, sa_column=sa.Column("response_status", sa.Integer(), nullable=True)
    )
    response_json: str | None = Field(
        default=None, sa_column=sa.Column("response_json", sa.Text(), nullable=True)
    )
    resource_id: str | None = Field(
        default=None, sa_column=sa.Column("resource_id", sa.Text(), nullable=True)
    )
    created_at: str = Field(sa_column=sa.Column("created_at", sa.Text(), nullable=False))
    expires_at: str = Field(sa_column=sa.Column("expires_at", sa.Text(), nullable=False))


metadata = SQLModel.metadata
