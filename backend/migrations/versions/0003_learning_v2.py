"""Upgrade managed v1 data without rewriting historical content.

Only databases at 0002_business_v1 are supported. An external user_version=1
is not evidence of this exact schema and must not be blindly stamped. All old
JSON, source hashes, IDs, timestamps, messages, citations and submissions remain
byte-for-byte unchanged. Old draft validation is intentionally invalidated.

Unknown-provenance fields are conservatively protected by top-level camelCase
paths (brief.<key>, roleCard.<key>, questionPlan); generation must treat a parent
path as protecting all descendants. Empty/null existing fields are protected too.
No provenance, event, report or student assertion is invented.

Downgrade is allowed only while all v2-only values are at migration defaults and
new tables empty. It cannot restore invalidated draft checks (unsafe under v1.1)
or recover any manual content history; restore the backup for an exact rollback.
"""

import json

import sqlalchemy as sa
from alembic import op

from migrations.schema_snapshots import create_v1, create_v2, indexes_v1, indexes_v2

revision = "0003_learning_v2"
down_revision = "0002_business_v1"
branch_labels = None
depends_on = None

REBUILT = ("task_versions", "role_sessions", "agent_runs", "review_records", "confirmations")
ADDED = ("learning_events", "learning_reports", "report_corrections")


def protected_fields(row, card):
    brief = json.loads(row["brief_json"])
    fields = [f"brief.{key}" for key in sorted(brief)] if isinstance(brief, dict) else ["brief"]
    if card is not None:
        value = json.loads(card)
        fields += (
            [f"roleCard.{key}" for key in sorted(value)]
            if isinstance(value, dict)
            else ["roleCard"]
        )
    fields.append("questionPlan")
    return json.dumps(fields, ensure_ascii=False, separators=(",", ":"))


def rebuild(table, version):
    bind = op.get_bind()
    columns = [c["name"] for c in sa.inspect(bind).get_columns(table)]
    create = create_v2 if version == 2 else create_v1
    create(table, physical_name=f"_migration_{table}")
    target = {c["name"] for c in sa.inspect(bind).get_columns(f"_migration_{table}")}
    common = ", ".join(f'"{name}"' for name in columns if name in target)
    bind.exec_driver_sql(
        f'INSERT INTO "_migration_{table}" ({common}) SELECT {common} FROM "{table}"'
    )
    op.drop_table(table)
    op.rename_table(f"_migration_{table}", table)
    (indexes_v2 if version == 2 else indexes_v1)(table)


def upgrade() -> None:
    for table in REBUILT:
        rebuild(table, 2)
    for table in ADDED:
        create_v2(table)
        indexes_v2(table)
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, brief_json FROM task_versions")).mappings().all()
    for row in rows:
        card = bind.execute(
            sa.text("SELECT card_json FROM role_cards WHERE version_id=:id"), {"id": row["id"]}
        ).scalar_one_or_none()
        bind.execute(
            sa.text("UPDATE task_versions SET manual_fields_json=:fields WHERE id=:id"),
            {"fields": protected_fields(row, card), "id": row["id"]},
        )
    bind.exec_driver_sql(
        "UPDATE task_versions SET validation_status='stale', validated_revision=NULL, "
        "preview_revision=NULL WHERE status='draft'"
    )
    bind.exec_driver_sql(
        "UPDATE role_sessions SET learning_revision=1 WHERE mode='student' AND EXISTS "
        "(SELECT 1 FROM messages WHERE messages.session_id=role_sessions.id AND speaker='user')"
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in ADDED:
        if bind.exec_driver_sql(f'SELECT 1 FROM "{table}" LIMIT 1').first():
            raise RuntimeError(
                "Cannot downgrade: v2 learning data exists; restore a backup instead"
            )
    conditions = {
        "agent_runs": "kind IN ('plan_generate','publish_preflight','learning_report')",
        "review_records": "kind='publish_preflight'",
        "confirmations": "action='replace_plan'",
        "task_versions": "teaching_intent<>'' OR generation_meta_json<>'{}'",
        "role_sessions": (
            "event_tracking_started_at IS NOT NULL OR learning_revision <> CASE WHEN "
            "mode='student' AND EXISTS (SELECT 1 FROM messages WHERE "
            "messages.session_id=role_sessions.id AND speaker='user') THEN 1 ELSE 0 END"
        ),
    }
    for table, condition in conditions.items():
        if bind.exec_driver_sql(f'SELECT 1 FROM "{table}" WHERE {condition} LIMIT 1').first():
            raise RuntimeError(f"Cannot downgrade: v2-only values in {table}; restore a backup")
    for row in bind.execute(sa.text("SELECT * FROM task_versions")).mappings():
        card = bind.execute(
            sa.text("SELECT card_json FROM role_cards WHERE version_id=:id"), {"id": row["id"]}
        ).scalar_one_or_none()
        if row["manual_fields_json"] != protected_fields(row, card):
            raise RuntimeError("Cannot downgrade: edited field provenance would be lost")
    for table in reversed(ADDED):
        op.drop_table(table)
    for table in REBUILT:
        rebuild(table, 1)
