"""Explicit, additive account initialization: python -m app.seed.

Run Alembic migrations first. Passwords are read only from process environment
INQUISPACE_SEED_{TEACHER,STUDENT1,STUDENT2}_PASSWORD or a non-echoing TTY prompt.
No password defaults, command-line password arguments, or automatic startup seed.
"""

import getpass
import os
import sys
import warnings
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import DateTime, Engine, MetaData, Table, inspect, select
from sqlalchemy.dialects.sqlite import insert

from app.core.config import BACKEND_DIR, Settings
from app.core.security import hash_password
from app.db.session import create_db_engine

ACCOUNTS = (
    ("teacher", "教师", "teacher"),
    ("student1", "学生一", "student"),
    ("student2", "学生二", "student"),
)


def read_password(username: str) -> str:
    variable = f"INQUISPACE_SEED_{username.upper()}_PASSWORD"
    password = os.environ.get(variable)
    if password is None:
        if not sys.stdin.isatty():
            raise ValueError(f"Set {variable} through a secure environment or use a terminal")
        # Never accept getpass's fallback to echoed stdin.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass(f"Password for {username}: ")
            confirmation = getpass.getpass(f"Confirm password for {username}: ")
        if password != confirmation:
            raise ValueError("Password confirmation does not match")
    if not password or password.isspace():
        raise ValueError("Password must not be blank")
    return password


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def require_schema_head(engine: Engine) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    expected = ScriptDirectory.from_config(config).get_current_head()
    if "alembic_version" not in inspect(engine).get_table_names():
        raise RuntimeError("Run migrations before initializing accounts")
    with engine.connect() as connection:
        current = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
    if current != expected:
        raise RuntimeError("Run migrations before initializing accounts")


def seed_accounts(engine: Engine, password_reader: Callable[[str], str] = read_password) -> int:
    """Insert missing fixed accounts atomically; never mutate any existing row."""
    require_schema_head(engine)
    users = Table("users", MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        existing = set(connection.execute(select(users.c.username)).scalars())
    rows = []
    now = utc_timestamp()
    for username, display_name, role in ACCOUNTS:
        if username in existing:
            continue
        rows.append(
            {
                "id": str(uuid4()),
                "username": username,
                "display_name": display_name,
                "role": role,
                "password_hash": hash_password(password_reader(username)),
                "is_active": True,
                "created_at": datetime.fromisoformat(now.replace("Z", "+00:00"))
                if isinstance(users.c.created_at.type, DateTime)
                else now,
                "updated_at": datetime.fromisoformat(now.replace("Z", "+00:00"))
                if isinstance(users.c.updated_at.type, DateTime)
                else now,
            }
        )
    created = 0
    with engine.begin() as connection:
        for row in rows:
            # A concurrent initializer must not replace credentials or identity either.
            result = connection.execute(
                insert(users).values(**row).on_conflict_do_nothing(index_elements=["username"])
            )
            created += result.rowcount
    return created


def main() -> int:
    engine = None
    try:
        settings = Settings()
        if not settings.database_path.is_file():
            raise RuntimeError("Run migrations before initializing accounts")
        engine = create_db_engine(settings)
        created = seed_accounts(engine)
    except (Exception, KeyboardInterrupt):
        # Database/validation exceptions may carry bound values; do not print them.
        print(
            "Account initialization failed; check migrations and secure password input. "
            "No existing accounts were changed.",
            file=sys.stderr,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print(f"Created {created} accounts; existing accounts were left unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
