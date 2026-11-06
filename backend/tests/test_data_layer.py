"""Real file migrations, frozen-v1 compatibility and database invariants."""

import json
import sqlite3

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlmodel import Session, select

from app.core.config import BACKEND_DIR
from app.db.models import User, metadata

NOW = "2026-11-04T00:00:00.000Z"
LATER = "2026-11-05T00:00:00.000Z"


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv("INQUISPACE_DATA_DIR", str(tmp_path))
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(cfg, "head")
    path = tmp_path / "inquispace.db"
    # Settings owns the configured basename; avoid assumptions about it.
    from app.core.config import Settings

    path = Settings().database_path
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    yield db, cfg, path
    db.close()


def insert(db, table, **values):
    values = dict(values)
    cols = {r[1] for r in db.execute(f'PRAGMA table_info("{table}")')}
    for name in ("created_at", "updated_at"):
        if name in cols:
            values.setdefault(name, NOW)
    db.execute(
        f'INSERT INTO "{table}" ({",".join(values)}) VALUES ({",".join("?" for _ in values)})',
        tuple(values.values()),
    )


def seed(db):
    for uid, role in [("teacher", "teacher"), ("student", "student")]:
        insert(db, "users", id=uid, username=uid, display_name=uid, role=role, password_hash="hash")
    for suffix in ("", "2"):
        insert(db, "tasks", id="t" + suffix, owner_id="teacher")
        insert(db, "task_versions", id="v" + suffix, task_id="t" + suffix, version_no=1)
        insert(
            db,
            "sources",
            id="source" + suffix,
            task_id="t" + suffix,
            uploaded_by="teacher",
            file_name="原文.txt",
            file_type="txt",
            byte_size=9,
            sha256="a" * 64,
            storage_key="file" + suffix,
        )
        insert(
            db,
            "role_sessions",
            id="s" + suffix,
            task_id="t" + suffix,
            version_id="v" + suffix,
            version_revision=1,
            owner_id="student",
            mode="student",
            snapshot_json='{"historical":"原文"}',
        )
        insert(
            db,
            "messages",
            id="u" + suffix,
            session_id="s" + suffix,
            seq=1,
            speaker="user",
            status="complete",
            text="学生自己的判断",
        )
    insert(
        db,
        "agent_runs",
        id="run",
        actor_id="student",
        task_id="t",
        version_id="v",
        version_revision=1,
        kind="chat",
        session_id="s",
        input_message_id="u",
        deadline_at=LATER,
    )
    insert(
        db,
        "messages",
        id="answer",
        session_id="s",
        seq=2,
        speaker="assistant",
        status="complete",
        run_id="run",
        text="原文",
        blocks_json='[{"text":"原文"}]',
    )
    db.execute("UPDATE agent_runs SET output_message_id='answer' WHERE id='run'")
    insert(
        db,
        "evidence",
        id="e",
        source_id="source",
        ordinal=1,
        text="原文",
        paragraph_no=1,
        start_line=1,
        end_line=1,
    )
    insert(
        db,
        "citations",
        id="cite",
        message_id="answer",
        block_index=0,
        evidence_id="e",
        quote="原文",
    )
    insert(db, "submissions", id="legacy", session_id="s", content_json=' {"conclusion": "原话"} ')
    db.commit()


def report(db, rid="report", **extra):
    values = dict(
        id=rid,
        session_id="s",
        report_no=1,
        kind="live",
        input_revision=1,
        input_hash="b" * 64,
        input_snapshot_json='{"student":"原话"}',
    )
    values.update(extra)
    insert(db, "learning_reports", **values)


def test_fresh_schema_and_sqlmodel(database):
    db, cfg, path = database
    assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0003_learning_v2"
    assert len(metadata.tables) == 23
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert db.execute("PRAGMA user_version").fetchone()[0] == 0
    engine = create_engine(f"sqlite:///{path}")
    try:
        with Session(engine) as session:
            session.add(
                User(
                    id="orm",
                    username="orm",
                    display_name="ORM",
                    role="teacher",
                    password_hash="hash",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            session.commit()
            assert session.exec(select(User)).one().is_active == 1
    finally:
        engine.dispose()
    command.upgrade(cfg, "head")


def schema_signature(db):
    result = {}
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        if name == "alembic_version":
            continue
        columns = [tuple(r)[1:] for r in db.execute(f'PRAGMA table_info("{name}")')]
        fks = sorted(tuple(r)[2:] for r in db.execute(f'PRAGMA foreign_key_list("{name}")'))
        indexes = []
        for row in db.execute(f'PRAGMA index_list("{name}")'):
            indexes.append(
                (
                    row[2],
                    tuple(tuple(x)[1:] for x in db.execute(f'PRAGMA index_xinfo("{row[1]}")')),
                    row[4],
                )
            )
        result[name] = (columns, fks, sorted(indexes))
    return result


def test_model_migration_and_document_schema_match(database):
    db, _, path = database
    model = sqlite3.connect(":memory:")
    engine = create_engine("sqlite://")
    for table in metadata.tables.values():
        model.execute(str(CreateTable(table).compile(engine)))
    for table in metadata.tables.values():
        for idx in table.indexes:
            model.execute(str(CreateIndex(idx).compile(engine)))
    assert schema_signature(db) == schema_signature(model)
    # The design DDL is an independent test oracle only, never a migration input.
    document = (BACKEND_DIR.parent / "docs/阶段一_数据库表设计.md").read_text()
    design = sqlite3.connect(":memory:")
    design.executescript(document.split("```sql\n")[1].split("```")[0])
    assert schema_signature(db) == schema_signature(design)
    live = inspect(create_engine(f"sqlite:///{path}"))
    expected = inspect(create_engine("sqlite://", creator=lambda: design))
    for name in metadata.tables:

        def normalize(checks):
            return sorted(" ".join(x["sqltext"].split()) for x in checks)

        assert normalize(live.get_check_constraints(name)) == normalize(
            expected.get_check_constraints(name)
        )
    model.close()
    design.close()
    engine.dispose()


@pytest.mark.parametrize(
    "table,values",
    [
        (
            "users",
            dict(id="bad", username="bad", display_name="bad", role="admin", password_hash="x"),
        ),
        ("task_versions", dict(id="duplicate", task_id="t", version_no=2)),
        ("version_sources", dict(task_id="t", version_id="v", source_id="source2")),
        (
            "role_sessions",
            dict(
                id="bad",
                task_id="t2",
                version_id="v",
                version_revision=1,
                owner_id="teacher",
                mode="preview",
                snapshot_json="{}",
            ),
        ),
        (
            "role_sessions",
            dict(
                id="bad",
                task_id="t",
                version_id="v",
                version_revision=1,
                owner_id="student",
                mode="student",
                snapshot_json="{}",
            ),
        ),
        (
            "messages",
            dict(
                id="bad",
                session_id="s2",
                seq=2,
                speaker="assistant",
                status="pending",
                run_id="run",
            ),
        ),
        ("messages", dict(id="bad", session_id="s", seq=3, speaker="user", status="pending")),
        (
            "messages",
            dict(
                id="bad", session_id="s", seq=3, speaker="user", status="complete", blocks_json="{"
            ),
        ),
        (
            "exploration_notes",
            dict(
                id="bad",
                session_id="s2",
                message_id="answer",
                block_index=0,
                original_view="x",
                answer_type="fact",
            ),
        ),
        ("evidence", dict(id="bad", source_id="source", ordinal=2, text="text", paragraph_no=1)),
        (
            "evidence",
            dict(id="bad", source_id="source", ordinal=2, text=" ", paragraph_no=1, page_no=1),
        ),
        (
            "citations",
            dict(id="bad", message_id="answer", block_index=0, evidence_id="e", quote="原文"),
        ),
        (
            "learning_events",
            dict(
                id="bad",
                session_id="s",
                event_type="stance",
                message_id="u2",
                value="agree_for_now",
            ),
        ),
        (
            "learning_events",
            dict(
                id="bad",
                session_id="s",
                event_type="source_open",
                source_id="source",
                value="agree_for_now",
            ),
        ),
        (
            "learning_events",
            dict(
                id="bad", session_id="s", event_type="stance", message_id="answer", value="invalid"
            ),
        ),
        (
            "learning_reports",
            dict(
                id="bad",
                session_id="s",
                report_no=1,
                kind="live",
                input_revision=1,
                input_hash="a" * 64,
                input_snapshot_json="[]",
            ),
        ),
        (
            "learning_reports",
            dict(
                id="bad",
                session_id="s",
                report_no=1,
                kind="live",
                input_revision=0,
                input_hash="a" * 64,
                input_snapshot_json="{}",
            ),
        ),
        (
            "report_corrections",
            dict(id="bad", session_id="s", report_id="absent", author_id="student", text="x"),
        ),
    ],
)
def test_declared_constraints(database, table, values):
    db, _, _ = database
    seed(db)
    with pytest.raises(sqlite3.IntegrityError):
        insert(db, table, **values)
    db.rollback()


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "bad", "session_id": "s2"},
        {"id": "bad", "step_count": 21},
        {"id": "bad", "deadline_at": NOW},
        {"id": "bad", "status": "completed"},
        {"id": "bad", "status": "waiting_confirmation"},
        {"id": "bad", "kind": "summary", "input_message_id": "u"},
        {"id": "bad"},
    ],
)
def test_run_constraints(database, changes):
    db, _, _ = database
    seed(db)
    values = dict(
        id="bad",
        actor_id="student",
        task_id="t",
        version_id="v",
        version_revision=1,
        kind="chat",
        session_id="s",
        input_message_id="u",
        deadline_at=LATER,
    )
    values.update(changes)
    with pytest.raises(sqlite3.IntegrityError):
        insert(db, "agent_runs", **values)
    db.rollback()


def test_reports_events_and_independent_concurrency(database):
    db, _, _ = database
    seed(db)
    insert(
        db,
        "agent_runs",
        id="rr",
        actor_id="student",
        task_id="t",
        version_id="v",
        version_revision=1,
        kind="learning_report",
        session_id="s",
        deadline_at=LATER,
    )
    report(db)
    insert(
        db,
        "learning_events",
        id="open",
        session_id="s",
        event_type="source_open",
        source_id="source",
    )
    insert(
        db,
        "learning_events",
        id="stance",
        session_id="s",
        event_type="stance",
        message_id="answer",
        value="agree_for_now",
    )
    db.commit()
    for table, values in [
        (
            "learning_events",
            dict(id="open2", session_id="s", event_type="source_open", source_id="source"),
        ),
        (
            "learning_events",
            dict(
                id="stance2",
                session_id="s",
                event_type="stance",
                message_id="answer",
                value="need_more_evidence",
            ),
        ),
        (
            "agent_runs",
            dict(
                id="rr2",
                actor_id="student",
                task_id="t",
                version_id="v",
                version_revision=1,
                kind="learning_report",
                session_id="s",
                deadline_at=LATER,
            ),
        ),
        (
            "report_corrections",
            dict(id="wrong", session_id="s2", report_id="report", author_id="student", text="x"),
        ),
    ]:
        with pytest.raises(sqlite3.IntegrityError):
            insert(db, table, **values)
        db.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        report(db, "same", report_no=2)
    db.rollback()
    report(db, "final", kind="final", report_no=2)
    db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        report(db, "final2", kind="final", report_no=3, input_revision=2)
    db.rollback()
    db.execute(
        "UPDATE learning_reports SET status='generating',generation_run_id='rr' WHERE id='report'"
    )
    db.execute(
        "UPDATE learning_reports SET status='ready',content_json='{}',generated_at=? "
        "WHERE id='report'",
        (NOW,),
    )
    insert(
        db,
        "report_corrections",
        id="correction",
        session_id="s",
        report_id="report",
        author_id="student",
        text="学生补充",
    )
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def snapshot(db, table):
    return [dict(r) for r in db.execute(f'SELECT * FROM "{table}" ORDER BY 1')]


def test_v1_upgrade_preserves_history_and_initializes_only_observed_data(database):
    db, cfg, _ = database
    command.downgrade(cfg, "0002_business_v1")
    seed(db)
    db.execute(
        "UPDATE task_versions SET brief_json=?, "
        "validation_status='valid',validated_revision=1,preview_revision=1 WHERE "
        "id='v'",
        (' {"subject":"历史","grade":"初一","region":null} ',),
    )
    insert(
        db,
        "role_cards",
        id="role",
        version_id="v",
        card_json=' {"name":"旧角色"} ',
        edited_by="teacher",
    )
    db.execute(
        "UPDATE task_versions SET "
        "status='published',validation_status='valid',validated_revision=1,preview_rev"
        "ision=1,content_hash='oldhash',published_at=?,published_by='teacher' WHERE "
        "id='v2'",
        (NOW,),
    )
    db.execute("UPDATE tasks SET current_published_version_id='v2' WHERE id='t2'")
    insert(
        db,
        "role_sessions",
        id="empty",
        task_id="t",
        version_id="v",
        version_revision=1,
        owner_id="teacher",
        mode="preview",
        snapshot_json="{}",
    )
    db.commit()
    tables = [
        r[0]
        for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        if r[0] not in ("alembic_version", "task_versions", "role_sessions")
    ]
    before = {t: snapshot(db, t) for t in tables}
    versions = snapshot(db, "task_versions")
    sessions = snapshot(db, "role_sessions")
    command.upgrade(cfg, "head")
    assert {t: snapshot(db, t) for t in tables} == before
    current = {r["id"]: r for r in snapshot(db, "task_versions")}
    for old in versions:
        new = current[old["id"]]
        for key, value in old.items():
            if old["status"] == "draft" and key in {
                "validation_status",
                "validated_revision",
                "preview_revision",
            }:
                continue
            assert new[key] == value
    draft = current["v"]
    assert draft["validation_status"] == "stale"
    assert draft["validated_revision"] is draft["preview_revision"] is None
    assert json.loads(draft["manual_fields_json"]) == [
        "brief.grade",
        "brief.region",
        "brief.subject",
        "roleCard.name",
        "questionPlan",
    ]
    assert draft["generation_meta_json"] == "{}" and draft["teaching_intent"] == ""
    for old, new in zip(sessions, snapshot(db, "role_sessions"), strict=True):
        assert all(new[k] == v for k, v in old.items())
        assert new["learning_revision"] == (0 if old["id"] == "empty" else 1)
        assert new["event_tracking_started_at"] is None
    for t in ("learning_events", "learning_reports", "report_corrections"):
        assert snapshot(db, t) == []
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    command.downgrade(cfg, "0002_business_v1")
    assert {t: snapshot(db, t) for t in tables} == before
    command.upgrade(cfg, "head")


def test_migration_failure_rolls_back_ddl_data_and_version(database, monkeypatch):
    db, cfg, _ = database
    command.downgrade(cfg, "0002_business_v1")
    seed(db)
    before = {
        r[0]: snapshot(db, r[0])
        for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    from migrations import schema_snapshots

    original = schema_snapshots.create_v2

    def fail(table, **kwargs):
        if table == "review_records":
            raise RuntimeError("injected rebuild failure")
        return original(table, **kwargs)

    monkeypatch.setattr(schema_snapshots, "create_v2", fail)
    with pytest.raises(RuntimeError, match="injected"):
        command.upgrade(cfg, "head")
    assert {
        r[0]: snapshot(db, r[0])
        for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    } == before
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    monkeypatch.setattr(schema_snapshots, "create_v2", original)
    command.upgrade(cfg, "head")


def test_unknown_legacy_database_not_adopted(database):
    db, cfg, _ = database
    command.downgrade(cfg, "base")
    db.execute("CREATE TABLE legacy_payload (id TEXT)")
    db.execute("PRAGMA user_version=1")
    db.commit()
    with pytest.raises(RuntimeError, match="Unrecognized legacy"):
        command.upgrade(cfg, "head")
    assert db.execute("SELECT version_num FROM alembic_version").fetchall() == []
    assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    assert db.execute("SELECT name FROM sqlite_master WHERE name='users'").fetchall() == []


def test_downgrade_refuses_loss_of_v2_data(database):
    db, cfg, _ = database
    seed(db)
    report(db)
    db.commit()
    with pytest.raises(RuntimeError, match="v2 learning data"):
        command.downgrade(cfg, "0002_business_v1")
    assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0003_learning_v2"
    assert len(snapshot(db, "learning_reports")) == 1


def test_end_and_report_enqueue_are_atomic(database):
    db, _, _ = database
    seed(db)
    with pytest.raises(sqlite3.IntegrityError):
        with db:
            db.execute(
                "UPDATE role_sessions SET "
                "status='ended',ended_at=?,learning_revision=1 WHERE id='s'",
                (NOW,),
            )
            report(db, kind="final", input_hash="invalid")
    assert db.execute("SELECT status FROM role_sessions WHERE id='s'").fetchone()[0] == "active"
    assert snapshot(db, "learning_reports") == []


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE task_versions SET teaching_intent='new intent'",
        "UPDATE task_versions SET manual_fields_json='[\"brief.subject\"]'",
        "UPDATE role_sessions SET learning_revision=2",
        "UPDATE role_sessions SET event_tracking_started_at='2026-11-04T00:00:00.000Z'",
    ],
)
def test_downgrade_rejects_v2_only_fields(database, sql):
    db, cfg, _ = database
    command.downgrade(cfg, "0002_business_v1")
    seed(db)
    command.upgrade(cfg, "head")
    db.execute(sql)
    db.commit()
    with pytest.raises(RuntimeError, match="Cannot downgrade"):
        command.downgrade(cfg, "0002_business_v1")
    assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0003_learning_v2"


def test_failed_report_does_not_reopen_ended_session(database):
    db, _, _ = database
    seed(db)
    with db:
        db.execute(
            "UPDATE role_sessions SET status='ended',ended_at=?,learning_revision=1 WHERE id='s'",
            (NOW,),
        )
        report(db, kind="final")
    with db:
        insert(
            db,
            "agent_runs",
            id="report-run",
            actor_id="student",
            task_id="t",
            version_id="v",
            version_revision=1,
            kind="learning_report",
            session_id="s",
            deadline_at=LATER,
        )
        db.execute("UPDATE learning_reports SET status='generating',generation_run_id='report-run'")
    with db:
        db.execute(
            "UPDATE agent_runs SET status='failed',finished_at=?,error_json='{}' "
            "WHERE id='report-run'",
            (NOW,),
        )
        db.execute("UPDATE learning_reports SET status='failed',error_json='{}'")
    assert db.execute("SELECT status FROM role_sessions WHERE id='s'").fetchone()[0] == "ended"
    original = snapshot(db, "learning_reports")[0]
    with db:
        db.execute(
            "UPDATE learning_reports SET status='queued',error_json=NULL,generation_run_id=NULL"
        )
    retried = snapshot(db, "learning_reports")[0]
    assert retried["input_snapshot_json"] == original["input_snapshot_json"]
    assert retried["id"] == original["id"]
    assert (
        db.execute("SELECT status FROM agent_runs WHERE id='report-run'").fetchone()[0] == "failed"
    )
    assert db.execute("SELECT text FROM messages WHERE id='u'").fetchone()[0] == "学生自己的判断"
