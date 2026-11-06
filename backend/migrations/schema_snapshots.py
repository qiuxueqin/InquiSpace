"""Frozen reviewed schema definitions for revisions 0002/0003 only.

Do not import application models here or change these after deployment.
The v1 boundary is the 20-table schema created by 0002, not arbitrary databases
claiming PRAGMA user_version=1. Unversioned external databases require a separate
inspected import; automatic stamping/adoption is deliberately unsupported.
"""

import sqlalchemy as sa
from alembic import op


def create_v1(table: str, physical_name: str | None = None) -> None:
    if table == "users":
        op.create_table(
            physical_name or "users",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("username", sa.Text(), nullable=False),
            sa.Column("display_name", sa.Text(), nullable=False),
            sa.Column("role", sa.Text(), nullable=False),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("username"),
            sa.CheckConstraint("role IN ('teacher','student')", name="ck_users_1"),
            sa.CheckConstraint("is_active IN (0,1)", name="ck_users_2"),
        )
        return
    if table == "login_sessions":
        op.create_table(
            physical_name or "login_sessions",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column("token_hash", sa.Text(), nullable=False),
            sa.Column("csrf_token", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.Text(), nullable=False),
            sa.Column("revoked_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.CheckConstraint("expires_at > created_at", name="ck_login_sessions_1"),
        )
        return
    if table == "tasks":
        op.create_table(
            physical_name or "tasks",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("owner_id", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
            sa.Column("row_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("current_published_version_id", sa.Text(), nullable=True),
            sa.Column("archived_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
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
                "(status = 'active' AND archived_at IS NULL) OR (status = 'archived' "
                "AND archived_at IS NOT NULL)",
                name="ck_tasks_3",
            ),
        )
        return
    if table == "task_members":
        op.create_table(
            physical_name or "task_members",
            sa.Column("task_id", sa.Text(), nullable=False),
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column("granted_by", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("task_id", "user_id"),
            sa.ForeignKeyConstraint(["granted_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        )
        return
    if table == "task_versions":
        op.create_table(
            physical_name or "task_versions",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("task_id", sa.Text(), nullable=False),
            sa.Column("version_no", sa.Integer(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
            sa.Column("from_version_id", sa.Text(), nullable=True),
            sa.Column("brief_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column(
                "question_plan_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")
            ),
            sa.Column(
                "validation_status", sa.Text(), nullable=False, server_default=sa.text("'stale'")
            ),
            sa.Column("validated_revision", sa.Integer(), nullable=True),
            sa.Column("preview_revision", sa.Integer(), nullable=True),
            sa.Column("content_hash", sa.Text(), nullable=True),
            sa.Column("published_at", sa.Text(), nullable=True),
            sa.Column("published_by", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("task_id", "version_no"),
            sa.UniqueConstraint("task_id", "id"),
            sa.ForeignKeyConstraint(["published_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["from_version_id"], ["task_versions.id"]),
            sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
            sa.CheckConstraint("version_no > 0", name="ck_task_versions_1"),
            sa.CheckConstraint("revision > 0", name="ck_task_versions_2"),
            sa.CheckConstraint("status IN ('draft','published')", name="ck_task_versions_3"),
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
                "preview_revision IS NULL OR preview_revision = revision",
                name="ck_task_versions_10",
            ),
            sa.CheckConstraint(
                "(status = 'draft' AND published_at IS NULL AND published_by IS NULL "
                "AND content_hash IS NULL) OR (status = 'published' AND published_at "
                "IS NOT NULL AND published_by IS NOT NULL AND content_hash IS NOT "
                "NULL AND validation_status = 'valid' AND preview_revision IS NOT "
                "NULL AND preview_revision = revision)",
                name="ck_task_versions_11",
            ),
        )
        return
    if table == "role_cards":
        op.create_table(
            physical_name or "role_cards",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("version_id", sa.Text(), nullable=False),
            sa.Column("card_json", sa.Text(), nullable=False),
            sa.Column("edited_by", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("version_id"),
            sa.ForeignKeyConstraint(["edited_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["version_id"], ["task_versions.id"]),
            sa.CheckConstraint("json_valid(card_json)", name="ck_role_cards_1"),
        )
        return
    if table == "sources":
        op.create_table(
            physical_name or "sources",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("task_id", sa.Text(), nullable=False),
            sa.Column("uploaded_by", sa.Text(), nullable=False),
            sa.Column("file_name", sa.Text(), nullable=False),
            sa.Column("file_type", sa.Text(), nullable=False),
            sa.Column("byte_size", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.Text(), nullable=False),
            sa.Column("storage_key", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'uploaded'")),
            sa.Column("page_count", sa.Integer(), nullable=True),
            sa.Column("total_lines", sa.Integer(), nullable=True),
            sa.Column("parser_version", sa.Text(), nullable=True),
            sa.Column("parse_error_json", sa.Text(), nullable=True),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
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
                "status <> 'ready' OR (parser_version IS NOT NULL AND ((file_type = "
                "'pdf' AND page_count IS NOT NULL) OR (file_type = 'txt' AND "
                "total_lines IS NOT NULL)))",
                name="ck_sources_10",
            ),
        )
        return
    if table == "version_sources":
        op.create_table(
            physical_name or "version_sources",
            sa.Column("task_id", sa.Text(), nullable=False),
            sa.Column("version_id", sa.Text(), nullable=False),
            sa.Column("source_id", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("version_id", "source_id"),
            sa.ForeignKeyConstraint(
                ["task_id", "version_id"], ["task_versions.task_id", "task_versions.id"]
            ),
            sa.ForeignKeyConstraint(["task_id", "source_id"], ["sources.task_id", "sources.id"]),
        )
        return
    if table == "evidence":
        op.create_table(
            physical_name or "evidence",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("source_id", sa.Text(), nullable=False),
            sa.Column("ordinal", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("page_no", sa.Integer(), nullable=True),
            sa.Column("paragraph_no", sa.Integer(), nullable=False),
            sa.Column("start_line", sa.Integer(), nullable=True),
            sa.Column("end_line", sa.Integer(), nullable=True),
            sa.Column("disputed", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source_id", "ordinal"),
            sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
            sa.CheckConstraint("ordinal > 0", name="ck_evidence_1"),
            sa.CheckConstraint("length(trim(text)) > 0", name="ck_evidence_2"),
            sa.CheckConstraint("page_no IS NULL OR page_no > 0", name="ck_evidence_3"),
            sa.CheckConstraint("paragraph_no > 0", name="ck_evidence_4"),
            sa.CheckConstraint("disputed IN (0,1)", name="ck_evidence_5"),
            sa.CheckConstraint(
                "(page_no IS NOT NULL AND start_line IS NULL AND end_line IS NULL) OR "
                "(page_no IS NULL AND start_line IS NOT NULL AND end_line IS NOT NULL "
                "AND start_line > 0 AND end_line >= start_line)",
                name="ck_evidence_6",
            ),
        )
        return
    if table == "role_sessions":
        op.create_table(
            physical_name or "role_sessions",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("task_id", sa.Text(), nullable=False),
            sa.Column("version_id", sa.Text(), nullable=False),
            sa.Column("version_revision", sa.Integer(), nullable=False),
            sa.Column("owner_id", sa.Text(), nullable=False),
            sa.Column("mode", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
            sa.Column("snapshot_json", sa.Text(), nullable=False),
            sa.Column("summary_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column(
                "summary_through_seq", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("completed_turns", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("ended_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
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
            sa.CheckConstraint(
                "(status = 'active' AND ended_at IS NULL) OR (status = 'ended' AND "
                "ended_at IS NOT NULL)",
                name="ck_role_sessions_9",
            ),
        )
        return
    if table == "messages":
        op.create_table(
            physical_name or "messages",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("session_id", sa.Text(), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("speaker", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("blocks_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("meta_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("run_id", sa.Text(), nullable=True),
            sa.Column("supersedes_message_id", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
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
                "supersedes_message_id IS NULL) OR (speaker = 'assistant' AND run_id "
                "IS NOT NULL)",
                name="ck_messages_6",
            ),
        )
        return
    if table == "citations":
        op.create_table(
            physical_name or "citations",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("message_id", sa.Text(), nullable=False),
            sa.Column("block_index", sa.Integer(), nullable=False),
            sa.Column("evidence_id", sa.Text(), nullable=False),
            sa.Column("quote", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("message_id", "block_index", "evidence_id"),
            sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"]),
            sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
            sa.CheckConstraint("block_index >= 0", name="ck_citations_1"),
            sa.CheckConstraint("length(trim(quote)) > 0", name="ck_citations_2"),
        )
        return
    if table == "exploration_notes":
        op.create_table(
            physical_name or "exploration_notes",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("session_id", sa.Text(), nullable=False),
            sa.Column("message_id", sa.Text(), nullable=False),
            sa.Column("block_index", sa.Integer(), nullable=False),
            sa.Column("original_view", sa.Text(), nullable=False),
            sa.Column("answer_type", sa.Text(), nullable=False),
            sa.Column(
                "evidence_ids_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")
            ),
            sa.Column("judgment", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column(
                "credibility", sa.Text(), nullable=False, server_default=sa.text("'unassessed'")
            ),
            sa.Column("limitations", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("row_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("deleted_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["message_id", "session_id"], ["messages.id", "messages.session_id"]
            ),
            sa.ForeignKeyConstraint(["session_id"], ["role_sessions.id"]),
            sa.CheckConstraint("block_index >= 0", name="ck_exploration_notes_1"),
            sa.CheckConstraint(
                "answer_type IN ('fact','opinion','inference','unknown')",
                name="ck_exploration_notes_2",
            ),
            sa.CheckConstraint("json_valid(evidence_ids_json)", name="ck_exploration_notes_3"),
            sa.CheckConstraint(
                "credibility IN ('unassessed','high','medium','low')", name="ck_exploration_notes_4"
            ),
            sa.CheckConstraint("row_version > 0", name="ck_exploration_notes_5"),
        )
        return
    if table == "submissions":
        op.create_table(
            physical_name or "submissions",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("session_id", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
            sa.Column("content_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("row_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("submitted_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("session_id"),
            sa.ForeignKeyConstraint(["session_id"], ["role_sessions.id"]),
            sa.CheckConstraint("status IN ('draft','submitted')", name="ck_submissions_1"),
            sa.CheckConstraint("json_valid(content_json)", name="ck_submissions_2"),
            sa.CheckConstraint("row_version > 0", name="ck_submissions_3"),
            sa.CheckConstraint(
                "(status = 'draft' AND submitted_at IS NULL) OR (status = 'submitted' "
                "AND submitted_at IS NOT NULL)",
                name="ck_submissions_4",
            ),
        )
        return
    if table == "agent_runs":
        op.create_table(
            physical_name or "agent_runs",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("actor_id", sa.Text(), nullable=False),
            sa.Column("task_id", sa.Text(), nullable=False),
            sa.Column("version_id", sa.Text(), nullable=False),
            sa.Column("version_revision", sa.Integer(), nullable=False),
            sa.Column("kind", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'running'")),
            sa.Column("session_id", sa.Text(), nullable=True),
            sa.Column("source_id", sa.Text(), nullable=True),
            sa.Column("input_message_id", sa.Text(), nullable=True),
            sa.Column("output_message_id", sa.Text(), nullable=True),
            sa.Column("retry_of_run_id", sa.Text(), nullable=True),
            sa.Column("step_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("max_steps", sa.Integer(), nullable=False, server_default=sa.text("20")),
            sa.Column("deadline_at", sa.Text(), nullable=False),
            sa.Column("cancel_requested_at", sa.Text(), nullable=True),
            sa.Column("terminal_reason", sa.Text(), nullable=True),
            sa.Column(
                "execution_config_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")
            ),
            sa.Column("result_json", sa.Text(), nullable=True),
            sa.Column("error_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("finished_at", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
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
                "kind IN ('parse_material','role_generate','role_validate','chat','summary')",
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
            sa.CheckConstraint(
                "error_json IS NULL OR json_valid(error_json)", name="ck_agent_runs_8"
            ),
            sa.CheckConstraint("step_count <= max_steps", name="ck_agent_runs_9"),
            sa.CheckConstraint("deadline_at > created_at", name="ck_agent_runs_10"),
            sa.CheckConstraint(
                "(kind IN ('chat','summary') AND session_id IS NOT NULL AND source_id "
                "IS NULL) OR (kind = 'parse_material' AND source_id IS NOT NULL AND "
                "session_id IS NULL) OR (kind IN ('role_generate','role_validate') "
                "AND session_id IS NULL AND source_id IS NULL)",
                name="ck_agent_runs_11",
            ),
            sa.CheckConstraint(
                "(kind = 'chat' AND input_message_id IS NOT NULL) OR (kind <> 'chat' "
                "AND input_message_id IS NULL AND output_message_id IS NULL AND "
                "retry_of_run_id IS NULL)",
                name="ck_agent_runs_12",
            ),
            sa.CheckConstraint(
                "status <> 'waiting_confirmation' OR (kind = 'role_generate' AND "
                "result_json IS NOT NULL)",
                name="ck_agent_runs_13",
            ),
            sa.CheckConstraint(
                "(status IN ('running','waiting_confirmation') AND finished_at IS "
                "NULL) OR (status IN ('completed','failed','cancelled') AND "
                "finished_at IS NOT NULL)",
                name="ck_agent_runs_14",
            ),
        )
        return
    if table == "run_steps":
        op.create_table(
            physical_name or "run_steps",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("run_id", sa.Text(), nullable=False),
            sa.Column("step_no", sa.Integer(), nullable=False),
            sa.Column("attempt", sa.Integer(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column(
                "input_summary_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")
            ),
            sa.Column("output_summary_json", sa.Text(), nullable=True),
            sa.Column("error_json", sa.Text(), nullable=True),
            sa.Column("started_at", sa.Text(), nullable=False),
            sa.Column("finished_at", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_id", "step_no", "attempt"),
            sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
            sa.CheckConstraint("step_no > 0", name="ck_run_steps_1"),
            sa.CheckConstraint("attempt BETWEEN 1 AND 3", name="ck_run_steps_2"),
            sa.CheckConstraint(
                "status IN ('running','completed','failed','cancelled')", name="ck_run_steps_3"
            ),
            sa.CheckConstraint("json_valid(input_summary_json)", name="ck_run_steps_4"),
            sa.CheckConstraint(
                "output_summary_json IS NULL OR json_valid(output_summary_json)",
                name="ck_run_steps_5",
            ),
            sa.CheckConstraint(
                "error_json IS NULL OR json_valid(error_json)", name="ck_run_steps_6"
            ),
            sa.CheckConstraint(
                "(status = 'running' AND finished_at IS NULL) OR (status <> 'running' "
                "AND finished_at IS NOT NULL)",
                name="ck_run_steps_7",
            ),
        )
        return
    if table == "run_events":
        op.create_table(
            physical_name or "run_events",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("run_id", sa.Text(), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.Text(), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_id", "seq"),
            sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
            sa.CheckConstraint("seq > 0", name="ck_run_events_1"),
            sa.CheckConstraint(
                "event_type IN "
                "('run.started','run.progress','answer.block','answer.meta','run.waiti"
                "ng_confirmation', 'run.completed','run.failed','run.cancelled')",
                name="ck_run_events_2",
            ),
            sa.CheckConstraint("json_valid(payload_json)", name="ck_run_events_3"),
        )
        return
    if table == "review_records":
        op.create_table(
            physical_name or "review_records",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("task_id", sa.Text(), nullable=False),
            sa.Column("version_id", sa.Text(), nullable=False),
            sa.Column("version_revision", sa.Integer(), nullable=False),
            sa.Column("kind", sa.Text(), nullable=False),
            sa.Column("session_id", sa.Text(), nullable=True),
            sa.Column("run_id", sa.Text(), nullable=True),
            sa.Column("message_id", sa.Text(), nullable=True),
            sa.Column("block_index", sa.Integer(), nullable=True),
            sa.Column("actor_id", sa.Text(), nullable=True),
            sa.Column("passed", sa.Integer(), nullable=True),
            sa.Column("result_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("issues_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
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
                "('role_validation','answer_check','preview_review','evaluation','busi"
                "ness_audit')",
                name="ck_review_records_2",
            ),
            sa.CheckConstraint(
                "block_index IS NULL OR block_index >= 0", name="ck_review_records_3"
            ),
            sa.CheckConstraint("passed IS NULL OR passed IN (0,1)", name="ck_review_records_4"),
            sa.CheckConstraint("json_valid(result_json)", name="ck_review_records_5"),
            sa.CheckConstraint("json_valid(issues_json)", name="ck_review_records_6"),
            sa.CheckConstraint(
                "message_id IS NULL OR session_id IS NOT NULL", name="ck_review_records_7"
            ),
            sa.CheckConstraint(
                "block_index IS NULL OR message_id IS NOT NULL", name="ck_review_records_8"
            ),
        )
        return
    if table == "confirmations":
        op.create_table(
            physical_name or "confirmations",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("task_id", sa.Text(), nullable=False),
            sa.Column("version_id", sa.Text(), nullable=False),
            sa.Column("version_revision", sa.Integer(), nullable=False),
            sa.Column("task_revision", sa.Integer(), nullable=False),
            sa.Column("actor_id", sa.Text(), nullable=False),
            sa.Column("action", sa.Text(), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("payload_hash", sa.Text(), nullable=False),
            sa.Column("content_hash", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.Text(), nullable=False),
            sa.Column("consumed_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["task_id", "version_id"], ["task_versions.task_id", "task_versions.id"]
            ),
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
            sa.CheckConstraint("version_revision > 0", name="ck_confirmations_1"),
            sa.CheckConstraint("task_revision > 0", name="ck_confirmations_2"),
            sa.CheckConstraint(
                "action IN ('publish_version','apply_role_candidate','archive_task')",
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
        )
        return
    if table == "idempotency_keys":
        op.create_table(
            physical_name or "idempotency_keys",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column("method", sa.Text(), nullable=False),
            sa.Column("path", sa.Text(), nullable=False),
            sa.Column("key", sa.Text(), nullable=False),
            sa.Column("request_hash", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("response_status", sa.Integer(), nullable=True),
            sa.Column("response_json", sa.Text(), nullable=True),
            sa.Column("resource_id", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "method", "path", "key"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.CheckConstraint("length(key) BETWEEN 1 AND 128", name="ck_idempotency_keys_1"),
            sa.CheckConstraint("length(request_hash) = 64", name="ck_idempotency_keys_2"),
            sa.CheckConstraint(
                "status IN ('in_progress','completed')", name="ck_idempotency_keys_3"
            ),
            sa.CheckConstraint(
                "response_status IS NULL OR response_status BETWEEN 200 AND 599",
                name="ck_idempotency_keys_4",
            ),
            sa.CheckConstraint(
                "response_json IS NULL OR json_valid(response_json)", name="ck_idempotency_keys_5"
            ),
            sa.CheckConstraint("expires_at > created_at", name="ck_idempotency_keys_6"),
            sa.CheckConstraint(
                "(status = 'in_progress' AND response_status IS NULL AND "
                "response_json IS NULL) OR (status = 'completed' AND response_status "
                "IS NOT NULL AND response_json IS NOT NULL)",
                name="ck_idempotency_keys_7",
            ),
        )
        return
    raise ValueError(f"Unknown frozen table: {table}")


def indexes_v1(table: str) -> None:
    if table == "login_sessions":
        op.create_index(
            "ix_login_user_expiry", "login_sessions", ["user_id", "expires_at"], unique=False
        )
    if table == "tasks":
        op.create_index(
            "ix_tasks_owner_list", "tasks", ["owner_id", "status", "created_at", "id"], unique=False
        )
    if table == "task_members":
        op.create_index("ix_members_user", "task_members", ["user_id", "task_id"], unique=False)
    if table == "task_versions":
        op.create_index(
            "uq_one_draft_per_task",
            "task_versions",
            ["task_id"],
            unique=True,
            sqlite_where=sa.text("status = 'draft'"),
        )
    if table == "sources":
        op.create_index(
            "ix_sources_task_list", "sources", ["task_id", "created_at", "id"], unique=False
        )
    if table == "version_sources":
        op.create_index("ix_version_sources_source", "version_sources", ["source_id"], unique=False)
    if table == "role_sessions":
        op.create_index(
            "ix_sessions_task_list",
            "role_sessions",
            ["task_id", "mode", "created_at", "id"],
            unique=False,
        )
        op.create_index("ix_sessions_version", "role_sessions", ["version_id"], unique=False)
        op.create_index(
            "uq_student_session",
            "role_sessions",
            ["owner_id", "version_id"],
            unique=True,
            sqlite_where=sa.text("mode = 'student'"),
        )
    if table == "citations":
        op.create_index("ix_citations_evidence", "citations", ["evidence_id"], unique=False)
    if table == "exploration_notes":
        op.create_index(
            "ix_notes_session_list",
            "exploration_notes",
            ["session_id", "created_at", "id"],
            unique=False,
            sqlite_where=sa.text("deleted_at IS NULL"),
        )
    if table == "agent_runs":
        op.create_index("ix_runs_actor_status", "agent_runs", ["actor_id", "status"], unique=False)
        op.create_index(
            "ix_runs_task_list", "agent_runs", ["task_id", "created_at", "id"], unique=False
        )
        op.create_index(
            "ix_runs_version", "agent_runs", ["version_id", "version_revision"], unique=False
        )
        op.create_index(
            "uq_completed_chat_question",
            "agent_runs",
            ["input_message_id"],
            unique=True,
            sqlite_where=sa.text("kind = 'chat' AND status = 'completed'"),
        )
        op.create_index(
            "uq_running_session",
            "agent_runs",
            ["session_id"],
            unique=True,
            sqlite_where=sa.text("status = 'running' AND kind IN ('chat','summary')"),
        )
        op.create_index(
            "uq_source_parsing_run",
            "agent_runs",
            ["source_id"],
            unique=True,
            sqlite_where=sa.text("kind = 'parse_material' AND status = 'running'"),
        )
    if table == "review_records":
        op.create_index(
            "ix_reviews_session_list",
            "review_records",
            ["session_id", "created_at", "id"],
            unique=False,
        )
        op.create_index(
            "ix_reviews_version_kind",
            "review_records",
            ["version_id", "version_revision", "kind"],
            unique=False,
        )
    if table == "confirmations":
        op.create_index("ix_confirmations_expiry", "confirmations", ["expires_at"], unique=False)
    if table == "idempotency_keys":
        op.create_index("ix_idempotency_expiry", "idempotency_keys", ["expires_at"], unique=False)


def create_v2(table: str, physical_name: str | None = None) -> None:
    if table == "users":
        op.create_table(
            physical_name or "users",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("username", sa.Text(), nullable=False),
            sa.Column("display_name", sa.Text(), nullable=False),
            sa.Column("role", sa.Text(), nullable=False),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("username"),
            sa.CheckConstraint("role IN ('teacher','student')", name="ck_users_1"),
            sa.CheckConstraint("is_active IN (0,1)", name="ck_users_2"),
        )
        return
    if table == "login_sessions":
        op.create_table(
            physical_name or "login_sessions",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column("token_hash", sa.Text(), nullable=False),
            sa.Column("csrf_token", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.Text(), nullable=False),
            sa.Column("revoked_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.CheckConstraint("expires_at > created_at", name="ck_login_sessions_1"),
        )
        return
    if table == "tasks":
        op.create_table(
            physical_name or "tasks",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("owner_id", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
            sa.Column("row_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("current_published_version_id", sa.Text(), nullable=True),
            sa.Column("archived_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
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
                "(status = 'active' AND archived_at IS NULL) OR (status = 'archived' "
                "AND archived_at IS NOT NULL)",
                name="ck_tasks_3",
            ),
        )
        return
    if table == "task_members":
        op.create_table(
            physical_name or "task_members",
            sa.Column("task_id", sa.Text(), nullable=False),
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column("granted_by", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("task_id", "user_id"),
            sa.ForeignKeyConstraint(["granted_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        )
        return
    if table == "task_versions":
        op.create_table(
            physical_name or "task_versions",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("task_id", sa.Text(), nullable=False),
            sa.Column("version_no", sa.Integer(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
            sa.Column("from_version_id", sa.Text(), nullable=True),
            sa.Column("teaching_intent", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column(
                "manual_fields_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")
            ),
            sa.Column(
                "generation_meta_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")
            ),
            sa.Column("brief_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column(
                "question_plan_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")
            ),
            sa.Column(
                "validation_status", sa.Text(), nullable=False, server_default=sa.text("'stale'")
            ),
            sa.Column("validated_revision", sa.Integer(), nullable=True),
            sa.Column("preview_revision", sa.Integer(), nullable=True),
            sa.Column("content_hash", sa.Text(), nullable=True),
            sa.Column("published_at", sa.Text(), nullable=True),
            sa.Column("published_by", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
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
                "preview_revision IS NULL OR preview_revision = revision",
                name="ck_task_versions_10",
            ),
            sa.CheckConstraint(
                "(status = 'draft' AND published_at IS NULL AND published_by IS NULL "
                "AND content_hash IS NULL) OR (status = 'published' AND published_at "
                "IS NOT NULL AND published_by IS NOT NULL AND content_hash IS NOT "
                "NULL AND validation_status = 'valid' AND preview_revision IS NOT "
                "NULL AND preview_revision = revision)",
                name="ck_task_versions_11",
            ),
        )
        return
    if table == "role_cards":
        op.create_table(
            physical_name or "role_cards",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("version_id", sa.Text(), nullable=False),
            sa.Column("card_json", sa.Text(), nullable=False),
            sa.Column("edited_by", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("version_id"),
            sa.ForeignKeyConstraint(["edited_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["version_id"], ["task_versions.id"]),
            sa.CheckConstraint("json_valid(card_json)", name="ck_role_cards_1"),
        )
        return
    if table == "sources":
        op.create_table(
            physical_name or "sources",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("task_id", sa.Text(), nullable=False),
            sa.Column("uploaded_by", sa.Text(), nullable=False),
            sa.Column("file_name", sa.Text(), nullable=False),
            sa.Column("file_type", sa.Text(), nullable=False),
            sa.Column("byte_size", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.Text(), nullable=False),
            sa.Column("storage_key", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'uploaded'")),
            sa.Column("page_count", sa.Integer(), nullable=True),
            sa.Column("total_lines", sa.Integer(), nullable=True),
            sa.Column("parser_version", sa.Text(), nullable=True),
            sa.Column("parse_error_json", sa.Text(), nullable=True),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
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
                "status <> 'ready' OR (parser_version IS NOT NULL AND ((file_type = "
                "'pdf' AND page_count IS NOT NULL) OR (file_type = 'txt' AND "
                "total_lines IS NOT NULL)))",
                name="ck_sources_10",
            ),
        )
        return
    if table == "version_sources":
        op.create_table(
            physical_name or "version_sources",
            sa.Column("task_id", sa.Text(), nullable=False),
            sa.Column("version_id", sa.Text(), nullable=False),
            sa.Column("source_id", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("version_id", "source_id"),
            sa.ForeignKeyConstraint(
                ["task_id", "version_id"], ["task_versions.task_id", "task_versions.id"]
            ),
            sa.ForeignKeyConstraint(["task_id", "source_id"], ["sources.task_id", "sources.id"]),
        )
        return
    if table == "evidence":
        op.create_table(
            physical_name or "evidence",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("source_id", sa.Text(), nullable=False),
            sa.Column("ordinal", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("page_no", sa.Integer(), nullable=True),
            sa.Column("paragraph_no", sa.Integer(), nullable=False),
            sa.Column("start_line", sa.Integer(), nullable=True),
            sa.Column("end_line", sa.Integer(), nullable=True),
            sa.Column("disputed", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source_id", "ordinal"),
            sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
            sa.CheckConstraint("ordinal > 0", name="ck_evidence_1"),
            sa.CheckConstraint("length(trim(text)) > 0", name="ck_evidence_2"),
            sa.CheckConstraint("page_no IS NULL OR page_no > 0", name="ck_evidence_3"),
            sa.CheckConstraint("paragraph_no > 0", name="ck_evidence_4"),
            sa.CheckConstraint("disputed IN (0,1)", name="ck_evidence_5"),
            sa.CheckConstraint(
                "(page_no IS NOT NULL AND start_line IS NULL AND end_line IS NULL) OR "
                "(page_no IS NULL AND start_line IS NOT NULL AND end_line IS NOT NULL "
                "AND start_line > 0 AND end_line >= start_line)",
                name="ck_evidence_6",
            ),
        )
        return
    if table == "role_sessions":
        op.create_table(
            physical_name or "role_sessions",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("task_id", sa.Text(), nullable=False),
            sa.Column("version_id", sa.Text(), nullable=False),
            sa.Column("version_revision", sa.Integer(), nullable=False),
            sa.Column("owner_id", sa.Text(), nullable=False),
            sa.Column("mode", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
            sa.Column("snapshot_json", sa.Text(), nullable=False),
            sa.Column("summary_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column(
                "summary_through_seq", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("completed_turns", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column(
                "learning_revision", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column("event_tracking_started_at", sa.Text(), nullable=True),
            sa.Column("ended_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
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
        )
        return
    if table == "messages":
        op.create_table(
            physical_name or "messages",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("session_id", sa.Text(), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("speaker", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("blocks_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("meta_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("run_id", sa.Text(), nullable=True),
            sa.Column("supersedes_message_id", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
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
                "supersedes_message_id IS NULL) OR (speaker = 'assistant' AND run_id "
                "IS NOT NULL)",
                name="ck_messages_6",
            ),
        )
        return
    if table == "citations":
        op.create_table(
            physical_name or "citations",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("message_id", sa.Text(), nullable=False),
            sa.Column("block_index", sa.Integer(), nullable=False),
            sa.Column("evidence_id", sa.Text(), nullable=False),
            sa.Column("quote", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("message_id", "block_index", "evidence_id"),
            sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"]),
            sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
            sa.CheckConstraint("block_index >= 0", name="ck_citations_1"),
            sa.CheckConstraint("length(trim(quote)) > 0", name="ck_citations_2"),
        )
        return
    if table == "exploration_notes":
        op.create_table(
            physical_name or "exploration_notes",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("session_id", sa.Text(), nullable=False),
            sa.Column("message_id", sa.Text(), nullable=False),
            sa.Column("block_index", sa.Integer(), nullable=False),
            sa.Column("original_view", sa.Text(), nullable=False),
            sa.Column("answer_type", sa.Text(), nullable=False),
            sa.Column(
                "evidence_ids_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")
            ),
            sa.Column("judgment", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column(
                "credibility", sa.Text(), nullable=False, server_default=sa.text("'unassessed'")
            ),
            sa.Column("limitations", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("row_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("deleted_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["message_id", "session_id"], ["messages.id", "messages.session_id"]
            ),
            sa.ForeignKeyConstraint(["session_id"], ["role_sessions.id"]),
            sa.CheckConstraint("block_index >= 0", name="ck_exploration_notes_1"),
            sa.CheckConstraint(
                "answer_type IN ('fact','opinion','inference','unknown')",
                name="ck_exploration_notes_2",
            ),
            sa.CheckConstraint("json_valid(evidence_ids_json)", name="ck_exploration_notes_3"),
            sa.CheckConstraint(
                "credibility IN ('unassessed','high','medium','low')", name="ck_exploration_notes_4"
            ),
            sa.CheckConstraint("row_version > 0", name="ck_exploration_notes_5"),
        )
        return
    if table == "submissions":
        op.create_table(
            physical_name or "submissions",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("session_id", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
            sa.Column("content_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("row_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("submitted_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("session_id"),
            sa.ForeignKeyConstraint(["session_id"], ["role_sessions.id"]),
            sa.CheckConstraint("status IN ('draft','submitted')", name="ck_submissions_1"),
            sa.CheckConstraint("json_valid(content_json)", name="ck_submissions_2"),
            sa.CheckConstraint("row_version > 0", name="ck_submissions_3"),
            sa.CheckConstraint(
                "(status = 'draft' AND submitted_at IS NULL) OR (status = 'submitted' "
                "AND submitted_at IS NOT NULL)",
                name="ck_submissions_4",
            ),
        )
        return
    if table == "learning_events":
        op.create_table(
            physical_name or "learning_events",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("session_id", sa.Text(), nullable=False),
            sa.Column("event_type", sa.Text(), nullable=False),
            sa.Column("source_id", sa.Text(), nullable=True),
            sa.Column("message_id", sa.Text(), nullable=True),
            sa.Column("value", sa.Text(), nullable=True),
            sa.Column("row_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["message_id", "session_id"], ["messages.id", "messages.session_id"]
            ),
            sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
            sa.ForeignKeyConstraint(["session_id"], ["role_sessions.id"]),
            sa.CheckConstraint(
                "event_type IN ('source_open','stance')", name="ck_learning_events_1"
            ),
            sa.CheckConstraint("row_version > 0", name="ck_learning_events_2"),
            sa.CheckConstraint(
                "(event_type = 'source_open' AND source_id IS NOT NULL AND message_id "
                "IS NULL AND value IS NULL) OR (event_type = 'stance' AND source_id "
                "IS NULL AND message_id IS NOT NULL AND value IS NOT NULL AND value "
                "IN ('need_more_evidence','agree_for_now','alternative_explanation'))",
                name="ck_learning_events_3",
            ),
        )
        return
    if table == "learning_reports":
        op.create_table(
            physical_name or "learning_reports",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("session_id", sa.Text(), nullable=False),
            sa.Column("report_no", sa.Integer(), nullable=False),
            sa.Column("kind", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
            sa.Column("input_revision", sa.Integer(), nullable=False),
            sa.Column("input_hash", sa.Text(), nullable=False),
            sa.Column("input_snapshot_json", sa.Text(), nullable=False),
            sa.Column("generation_run_id", sa.Text(), nullable=True),
            sa.Column("content_json", sa.Text(), nullable=True),
            sa.Column("error_json", sa.Text(), nullable=True),
            sa.Column("generated_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
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
                "(status = 'ready' AND content_json IS NOT NULL AND generated_at IS "
                "NOT NULL) OR (status <> 'ready' AND content_json IS NULL AND "
                "generated_at IS NULL)",
                name="ck_learning_reports_9",
            ),
            sa.CheckConstraint(
                "(status = 'failed' AND error_json IS NOT NULL) OR (status <> "
                "'failed' AND error_json IS NULL)",
                name="ck_learning_reports_10",
            ),
            sa.CheckConstraint(
                "(status IN ('queued','superseded') AND generation_run_id IS NULL) OR "
                "(status IN ('generating','ready','failed') AND generation_run_id IS "
                "NOT NULL)",
                name="ck_learning_reports_11",
            ),
        )
        return
    if table == "report_corrections":
        op.create_table(
            physical_name or "report_corrections",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("session_id", sa.Text(), nullable=False),
            sa.Column("report_id", sa.Text(), nullable=False),
            sa.Column("author_id", sa.Text(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["report_id", "session_id"], ["learning_reports.id", "learning_reports.session_id"]
            ),
            sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["session_id"], ["role_sessions.id"]),
            sa.CheckConstraint(
                "length(trim(text)) BETWEEN 1 AND 2000", name="ck_report_corrections_1"
            ),
        )
        return
    if table == "agent_runs":
        op.create_table(
            physical_name or "agent_runs",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("actor_id", sa.Text(), nullable=False),
            sa.Column("task_id", sa.Text(), nullable=False),
            sa.Column("version_id", sa.Text(), nullable=False),
            sa.Column("version_revision", sa.Integer(), nullable=False),
            sa.Column("kind", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'running'")),
            sa.Column("session_id", sa.Text(), nullable=True),
            sa.Column("source_id", sa.Text(), nullable=True),
            sa.Column("input_message_id", sa.Text(), nullable=True),
            sa.Column("output_message_id", sa.Text(), nullable=True),
            sa.Column("retry_of_run_id", sa.Text(), nullable=True),
            sa.Column("step_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("max_steps", sa.Integer(), nullable=False, server_default=sa.text("20")),
            sa.Column("deadline_at", sa.Text(), nullable=False),
            sa.Column("cancel_requested_at", sa.Text(), nullable=True),
            sa.Column("terminal_reason", sa.Text(), nullable=True),
            sa.Column(
                "execution_config_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")
            ),
            sa.Column("result_json", sa.Text(), nullable=True),
            sa.Column("error_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("finished_at", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
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
                "('parse_material','role_generate','role_validate','plan_generate','pu"
                "blish_preflight','chat','summary','learning_report')",
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
            sa.CheckConstraint(
                "error_json IS NULL OR json_valid(error_json)", name="ck_agent_runs_8"
            ),
            sa.CheckConstraint("step_count <= max_steps", name="ck_agent_runs_9"),
            sa.CheckConstraint("deadline_at > created_at", name="ck_agent_runs_10"),
            sa.CheckConstraint(
                "(kind IN ('chat','summary','learning_report') AND session_id IS NOT "
                "NULL AND source_id IS NULL) OR (kind = 'parse_material' AND "
                "source_id IS NOT NULL AND session_id IS NULL) OR (kind IN "
                "('role_generate','role_validate','plan_generate','publish_preflight')"
                " AND session_id IS NULL AND source_id IS NULL)",
                name="ck_agent_runs_11",
            ),
            sa.CheckConstraint(
                "(kind = 'chat' AND input_message_id IS NOT NULL) OR (kind <> 'chat' "
                "AND input_message_id IS NULL AND output_message_id IS NULL AND "
                "retry_of_run_id IS NULL)",
                name="ck_agent_runs_12",
            ),
            sa.CheckConstraint(
                "status <> 'waiting_confirmation' OR (kind = 'role_generate' AND "
                "result_json IS NOT NULL)",
                name="ck_agent_runs_13",
            ),
            sa.CheckConstraint(
                "(status IN ('running','waiting_confirmation') AND finished_at IS "
                "NULL) OR (status IN ('completed','failed','cancelled') AND "
                "finished_at IS NOT NULL)",
                name="ck_agent_runs_14",
            ),
        )
        return
    if table == "run_steps":
        op.create_table(
            physical_name or "run_steps",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("run_id", sa.Text(), nullable=False),
            sa.Column("step_no", sa.Integer(), nullable=False),
            sa.Column("attempt", sa.Integer(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column(
                "input_summary_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")
            ),
            sa.Column("output_summary_json", sa.Text(), nullable=True),
            sa.Column("error_json", sa.Text(), nullable=True),
            sa.Column("started_at", sa.Text(), nullable=False),
            sa.Column("finished_at", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_id", "step_no", "attempt"),
            sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
            sa.CheckConstraint("step_no > 0", name="ck_run_steps_1"),
            sa.CheckConstraint("attempt BETWEEN 1 AND 3", name="ck_run_steps_2"),
            sa.CheckConstraint(
                "status IN ('running','completed','failed','cancelled')", name="ck_run_steps_3"
            ),
            sa.CheckConstraint("json_valid(input_summary_json)", name="ck_run_steps_4"),
            sa.CheckConstraint(
                "output_summary_json IS NULL OR json_valid(output_summary_json)",
                name="ck_run_steps_5",
            ),
            sa.CheckConstraint(
                "error_json IS NULL OR json_valid(error_json)", name="ck_run_steps_6"
            ),
            sa.CheckConstraint(
                "(status = 'running' AND finished_at IS NULL) OR (status <> 'running' "
                "AND finished_at IS NOT NULL)",
                name="ck_run_steps_7",
            ),
        )
        return
    if table == "run_events":
        op.create_table(
            physical_name or "run_events",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("run_id", sa.Text(), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.Text(), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_id", "seq"),
            sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
            sa.CheckConstraint("seq > 0", name="ck_run_events_1"),
            sa.CheckConstraint(
                "event_type IN "
                "('run.started','run.progress','answer.block','answer.meta','run.waiti"
                "ng_confirmation', 'run.completed','run.failed','run.cancelled')",
                name="ck_run_events_2",
            ),
            sa.CheckConstraint("json_valid(payload_json)", name="ck_run_events_3"),
        )
        return
    if table == "review_records":
        op.create_table(
            physical_name or "review_records",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("task_id", sa.Text(), nullable=False),
            sa.Column("version_id", sa.Text(), nullable=False),
            sa.Column("version_revision", sa.Integer(), nullable=False),
            sa.Column("kind", sa.Text(), nullable=False),
            sa.Column("session_id", sa.Text(), nullable=True),
            sa.Column("run_id", sa.Text(), nullable=True),
            sa.Column("message_id", sa.Text(), nullable=True),
            sa.Column("block_index", sa.Integer(), nullable=True),
            sa.Column("actor_id", sa.Text(), nullable=True),
            sa.Column("passed", sa.Integer(), nullable=True),
            sa.Column("result_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("issues_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
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
                "('role_validation','answer_check','preview_review','publish_preflight"
                "','evaluation','business_audit')",
                name="ck_review_records_2",
            ),
            sa.CheckConstraint(
                "block_index IS NULL OR block_index >= 0", name="ck_review_records_3"
            ),
            sa.CheckConstraint("passed IS NULL OR passed IN (0,1)", name="ck_review_records_4"),
            sa.CheckConstraint("json_valid(result_json)", name="ck_review_records_5"),
            sa.CheckConstraint("json_valid(issues_json)", name="ck_review_records_6"),
            sa.CheckConstraint(
                "message_id IS NULL OR session_id IS NOT NULL", name="ck_review_records_7"
            ),
            sa.CheckConstraint(
                "block_index IS NULL OR message_id IS NOT NULL", name="ck_review_records_8"
            ),
        )
        return
    if table == "confirmations":
        op.create_table(
            physical_name or "confirmations",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("task_id", sa.Text(), nullable=False),
            sa.Column("version_id", sa.Text(), nullable=False),
            sa.Column("version_revision", sa.Integer(), nullable=False),
            sa.Column("task_revision", sa.Integer(), nullable=False),
            sa.Column("actor_id", sa.Text(), nullable=False),
            sa.Column("action", sa.Text(), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("payload_hash", sa.Text(), nullable=False),
            sa.Column("content_hash", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.Text(), nullable=False),
            sa.Column("consumed_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["task_id", "version_id"], ["task_versions.task_id", "task_versions.id"]
            ),
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
            sa.CheckConstraint("version_revision > 0", name="ck_confirmations_1"),
            sa.CheckConstraint("task_revision > 0", name="ck_confirmations_2"),
            sa.CheckConstraint(
                "action IN "
                "('publish_version','apply_role_candidate','archive_task','replace_pla"
                "n')",
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
        )
        return
    if table == "idempotency_keys":
        op.create_table(
            physical_name or "idempotency_keys",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column("method", sa.Text(), nullable=False),
            sa.Column("path", sa.Text(), nullable=False),
            sa.Column("key", sa.Text(), nullable=False),
            sa.Column("request_hash", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("response_status", sa.Integer(), nullable=True),
            sa.Column("response_json", sa.Text(), nullable=True),
            sa.Column("resource_id", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "method", "path", "key"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.CheckConstraint("length(key) BETWEEN 1 AND 128", name="ck_idempotency_keys_1"),
            sa.CheckConstraint("length(request_hash) = 64", name="ck_idempotency_keys_2"),
            sa.CheckConstraint(
                "status IN ('in_progress','completed')", name="ck_idempotency_keys_3"
            ),
            sa.CheckConstraint(
                "response_status IS NULL OR response_status BETWEEN 200 AND 599",
                name="ck_idempotency_keys_4",
            ),
            sa.CheckConstraint(
                "response_json IS NULL OR json_valid(response_json)", name="ck_idempotency_keys_5"
            ),
            sa.CheckConstraint("expires_at > created_at", name="ck_idempotency_keys_6"),
            sa.CheckConstraint(
                "(status = 'in_progress' AND response_status IS NULL AND "
                "response_json IS NULL) OR (status = 'completed' AND response_status "
                "IS NOT NULL AND response_json IS NOT NULL)",
                name="ck_idempotency_keys_7",
            ),
        )
        return
    raise ValueError(f"Unknown frozen table: {table}")


def indexes_v2(table: str) -> None:
    if table == "login_sessions":
        op.create_index(
            "ix_login_user_expiry", "login_sessions", ["user_id", "expires_at"], unique=False
        )
    if table == "tasks":
        op.create_index(
            "ix_tasks_owner_list", "tasks", ["owner_id", "status", "created_at", "id"], unique=False
        )
    if table == "task_members":
        op.create_index("ix_members_user", "task_members", ["user_id", "task_id"], unique=False)
    if table == "task_versions":
        op.create_index(
            "uq_one_draft_per_task",
            "task_versions",
            ["task_id"],
            unique=True,
            sqlite_where=sa.text("status = 'draft'"),
        )
    if table == "sources":
        op.create_index(
            "ix_sources_task_list", "sources", ["task_id", "created_at", "id"], unique=False
        )
    if table == "version_sources":
        op.create_index("ix_version_sources_source", "version_sources", ["source_id"], unique=False)
    if table == "role_sessions":
        op.create_index(
            "ix_sessions_task_list",
            "role_sessions",
            ["task_id", "mode", "created_at", "id"],
            unique=False,
        )
        op.create_index("ix_sessions_version", "role_sessions", ["version_id"], unique=False)
        op.create_index(
            "uq_student_session",
            "role_sessions",
            ["owner_id", "version_id"],
            unique=True,
            sqlite_where=sa.text("mode = 'student'"),
        )
    if table == "citations":
        op.create_index("ix_citations_evidence", "citations", ["evidence_id"], unique=False)
    if table == "exploration_notes":
        op.create_index(
            "ix_notes_session_list",
            "exploration_notes",
            ["session_id", "created_at", "id"],
            unique=False,
            sqlite_where=sa.text("deleted_at IS NULL"),
        )
    if table == "learning_events":
        op.create_index(
            "ix_learning_events_session",
            "learning_events",
            ["session_id", "event_type", "updated_at"],
            unique=False,
        )
        op.create_index(
            "uq_source_open_event",
            "learning_events",
            ["session_id", "source_id"],
            unique=True,
            sqlite_where=sa.text("event_type = 'source_open'"),
        )
        op.create_index(
            "uq_stance_event",
            "learning_events",
            ["session_id", "message_id"],
            unique=True,
            sqlite_where=sa.text("event_type = 'stance'"),
        )
    if table == "learning_reports":
        op.create_index(
            "ix_learning_reports_latest",
            "learning_reports",
            ["session_id", "kind", sa.text("input_revision DESC")],
            unique=False,
        )
        op.create_index(
            "ix_learning_reports_queue",
            "learning_reports",
            ["status", "created_at", "id"],
            unique=False,
        )
        op.create_index(
            "uq_final_learning_report",
            "learning_reports",
            ["session_id"],
            unique=True,
            sqlite_where=sa.text("kind = 'final'"),
        )
    if table == "report_corrections":
        op.create_index(
            "ix_report_corrections_session",
            "report_corrections",
            ["session_id", "created_at", "id"],
            unique=False,
        )
    if table == "agent_runs":
        op.create_index("ix_runs_actor_status", "agent_runs", ["actor_id", "status"], unique=False)
        op.create_index(
            "ix_runs_task_list", "agent_runs", ["task_id", "created_at", "id"], unique=False
        )
        op.create_index(
            "ix_runs_version", "agent_runs", ["version_id", "version_revision"], unique=False
        )
        op.create_index(
            "uq_completed_chat_question",
            "agent_runs",
            ["input_message_id"],
            unique=True,
            sqlite_where=sa.text("kind = 'chat' AND status = 'completed'"),
        )
        op.create_index(
            "uq_running_report",
            "agent_runs",
            ["session_id"],
            unique=True,
            sqlite_where=sa.text("status = 'running' AND kind = 'learning_report'"),
        )
        op.create_index(
            "uq_running_session",
            "agent_runs",
            ["session_id"],
            unique=True,
            sqlite_where=sa.text("status = 'running' AND kind IN ('chat','summary')"),
        )
        op.create_index(
            "uq_running_version_workflow",
            "agent_runs",
            ["version_id", "version_revision", "kind"],
            unique=True,
            sqlite_where=sa.text(
                "status = 'running' AND kind IN "
                "('plan_generate','publish_preflight','role_validate')"
            ),
        )
        op.create_index(
            "uq_source_parsing_run",
            "agent_runs",
            ["source_id"],
            unique=True,
            sqlite_where=sa.text("kind = 'parse_material' AND status = 'running'"),
        )
    if table == "review_records":
        op.create_index(
            "ix_reviews_session_list",
            "review_records",
            ["session_id", "created_at", "id"],
            unique=False,
        )
        op.create_index(
            "ix_reviews_version_kind",
            "review_records",
            ["version_id", "version_revision", "kind"],
            unique=False,
        )
    if table == "confirmations":
        op.create_index("ix_confirmations_expiry", "confirmations", ["expires_at"], unique=False)
    if table == "idempotency_keys":
        op.create_index("ix_idempotency_expiry", "idempotency_keys", ["expires_at"], unique=False)


V1_TABLES = (
    "users",
    "login_sessions",
    "tasks",
    "task_members",
    "task_versions",
    "role_cards",
    "sources",
    "version_sources",
    "evidence",
    "role_sessions",
    "messages",
    "citations",
    "exploration_notes",
    "submissions",
    "agent_runs",
    "run_steps",
    "run_events",
    "review_records",
    "confirmations",
    "idempotency_keys",
)
V2_TABLES = (
    "users",
    "login_sessions",
    "tasks",
    "task_members",
    "task_versions",
    "role_cards",
    "sources",
    "version_sources",
    "evidence",
    "role_sessions",
    "messages",
    "citations",
    "exploration_notes",
    "submissions",
    "learning_events",
    "learning_reports",
    "report_corrections",
    "agent_runs",
    "run_steps",
    "run_events",
    "review_records",
    "confirmations",
    "idempotency_keys",
)
