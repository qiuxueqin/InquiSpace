import sqlite3

from sqlalchemy import Engine, event
from sqlmodel import create_engine

from app.core.config import Settings


def create_db_engine(settings: Settings) -> Engine:
    engine = create_engine(
        f"sqlite:///{settings.database_path.as_posix()}",
        connect_args={
            "check_same_thread": False,
            "timeout": settings.sqlite_busy_timeout_ms / 1000,
        },
    )

    @event.listens_for(engine, "connect")
    def configure_connection(connection: sqlite3.Connection, _record: object) -> None:
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
            # This factory opens file databases only. Memory SQLite cannot use WAL.
            mode = cursor.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if mode.lower() != "wal":
                raise RuntimeError("File SQLite databases require WAL journal mode")
        finally:
            cursor.close()

    return engine


def initialize_storage(settings: Settings, engine: Engine) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "uploads").mkdir(exist_ok=True)
    with engine.connect() as connection:
        if connection.exec_driver_sql("SELECT json_valid('{}')").scalar_one() != 1:
            raise RuntimeError("SQLite JSON functions are required")
