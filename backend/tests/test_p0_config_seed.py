import getpass
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import MetaData, Table, select

from app import seed
from app.core.config import BACKEND_DIR, Settings
from app.core.security import hash_password, verify_password
from app.db.session import create_db_engine, initialize_storage

POSITIVE_FIELDS = (
    "max_sources_per_version",
    "max_upload_bytes",
    "max_pdf_pages",
    "model_timeout_seconds",
    "parse_timeout_seconds",
    "run_timeout_seconds",
    "run_max_steps",
    "confirmation_ttl_seconds",
    "model_max_concurrency",
    "sqlite_busy_timeout_ms",
    "default_duration_minutes",
    "default_max_turns",
)


@pytest.mark.parametrize("field", POSITIVE_FIELDS)
@pytest.mark.parametrize("value", [0, -1])
def test_config_requires_positive_values(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_config_defaults_and_environment(monkeypatch):
    settings = Settings(_env_file=None)
    assert settings.max_upload_bytes == 10 * 1024 * 1024
    assert settings.max_sources_per_version == 10
    assert settings.max_pdf_pages == 100
    assert settings.model_timeout_seconds == 60
    assert settings.parse_timeout_seconds == 60
    assert settings.run_timeout_seconds == 180
    assert settings.run_max_steps == 20
    assert settings.confirmation_ttl_seconds == 1800
    monkeypatch.setenv("INQUISPACE_DEFAULT_DURATION_MINUTES", "35")
    assert Settings(_env_file=None).default_duration_minutes == 35
    with pytest.raises(ValidationError):
        Settings(_env_file=None, default_subject="  ")


def test_file_sqlite_wal_and_busy_timeout(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, sqlite_busy_timeout_ms=1234)
    engine = create_db_engine(settings)
    try:
        initialize_storage(settings, engine)
        with engine.connect() as connection, engine.connect() as second:
            for conn in (connection, second):
                assert conn.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
                assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
                assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 1234
    finally:
        engine.dispose()
    engine = create_db_engine(settings)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
    finally:
        engine.dispose()


@pytest.fixture
def migrated_engine(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("INQUISPACE_DATA_DIR", str(tmp_path))
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_db_engine(Settings(_env_file=None, data_dir=tmp_path))
    yield engine
    engine.dispose()


def test_seed_requires_current_migration_head(tmp_path, monkeypatch):
    monkeypatch.setenv("INQUISPACE_DATA_DIR", str(tmp_path))
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(config, "0002_business_v1")
    engine = create_db_engine(Settings(_env_file=None, data_dir=tmp_path))
    try:
        with pytest.raises(RuntimeError, match="Run migrations"):
            seed.seed_accounts(engine, lambda _username: str(uuid4()))
    finally:
        engine.dispose()


def test_seed_rejects_database_without_alembic_history(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    engine = create_db_engine(settings)
    try:
        initialize_storage(settings, engine)
        with pytest.raises(RuntimeError, match="Run migrations"):
            seed.seed_accounts(engine, lambda _username: str(uuid4()))
    finally:
        engine.dispose()


def test_seed_hashes_and_never_overwrites_existing_identity(migrated_engine):
    passwords = {username: str(uuid4()) for username, _, _ in seed.ACCOUNTS}
    assert seed.seed_accounts(migrated_engine, passwords.__getitem__) == 3
    users = Table("users", MetaData(), autoload_with=migrated_engine)
    with migrated_engine.begin() as connection:
        rows = connection.execute(select(users)).mappings().all()
        assert len(rows) == 3
        assert sorted(row["role"] for row in rows) == ["student", "student", "teacher"]
        for row in rows:
            assert row["password_hash"].startswith("$argon2id$")
            assert verify_password(row["password_hash"], passwords[row["username"]])
            assert row["created_at"].endswith("Z")
            assert row["updated_at"].endswith("Z")
        connection.execute(
            users.update()
            .where(users.c.username == "teacher")
            .values(role="student", display_name="保留身份", is_active=False)
        )
        before = connection.execute(select(users).order_by(users.c.username)).all()

    def never_prompt(_username):
        pytest.fail("Existing accounts must not require or reset passwords")

    assert seed.seed_accounts(migrated_engine, never_prompt) == 0
    with migrated_engine.connect() as connection:
        assert connection.execute(select(users).order_by(users.c.username)).all() == before


def test_seed_bad_password_is_atomic(migrated_engine):
    def password_reader(username):
        return " " if username == "student2" else str(uuid4())

    with pytest.raises(ValueError):
        seed.seed_accounts(migrated_engine, password_reader)
    users = Table("users", MetaData(), autoload_with=migrated_engine)
    with migrated_engine.connect() as connection:
        assert connection.execute(select(users)).all() == []


def test_password_hash_random_salt_and_verification():
    password = str(uuid4())
    first = hash_password(password)
    assert first != hash_password(password)
    assert verify_password(first, password)
    assert not verify_password(first, str(uuid4()))
    assert not verify_password("invalid-hash", password)


def test_password_input_environment_and_noninteractive(monkeypatch):
    password = str(uuid4())
    monkeypatch.setenv("INQUISPACE_SEED_TEACHER_PASSWORD", password)
    assert seed.read_password("teacher") == password
    monkeypatch.delenv("INQUISPACE_SEED_TEACHER_PASSWORD")
    monkeypatch.setattr(seed.sys.stdin, "isatty", lambda: False)
    with pytest.raises(ValueError, match="secure environment"):
        seed.read_password("teacher")


def test_password_input_rejects_echo_fallback(monkeypatch):
    monkeypatch.delenv("INQUISPACE_SEED_TEACHER_PASSWORD", raising=False)
    monkeypatch.setattr(seed.sys.stdin, "isatty", lambda: True)

    def fallback(_prompt):
        import warnings

        warnings.warn("Cannot control echo", getpass.GetPassWarning, stacklevel=2)
        pytest.fail("Must stop before reading an echoed password")

    monkeypatch.setattr(seed.getpass, "getpass", fallback)
    with pytest.raises(getpass.GetPassWarning):
        seed.read_password("teacher")


def test_cli_does_not_create_unmigrated_database(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("INQUISPACE_DATA_DIR", str(tmp_path))
    assert seed.main() == 1
    assert not (tmp_path / "inquispace.db").exists()
    assert "initialization failed" in capsys.readouterr().err


def test_cli_success_and_rerun_without_credentials(migrated_engine, monkeypatch, capsys):
    secrets = []
    for username, _, _ in seed.ACCOUNTS:
        password = str(uuid4())
        secrets.append(password)
        monkeypatch.setenv(f"INQUISPACE_SEED_{username.upper()}_PASSWORD", password)
    assert seed.main() == 0
    for username, _, _ in seed.ACCOUNTS:
        monkeypatch.delenv(f"INQUISPACE_SEED_{username.upper()}_PASSWORD")
    assert seed.main() == 0
    output = capsys.readouterr()
    assert "Created 3 accounts" in output.out
    assert "Created 0 accounts" in output.out
    assert not output.err
    assert all(password not in output.out for password in secrets)
