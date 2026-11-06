"""Offline, single-writer SQLite migrations with an atomic DDL transaction.

Stop the application and back up the database plus uploads before migrating.
Foreign keys must be disabled *before* BEGIN for cyclic table rebuilds. They are
checked before commit and restored afterwards, even on failure. Explicit BEGIN
avoids sqlite3 legacy transaction mode autocommitting CREATE/DROP statements.
Alembic's version row is committed in the same transaction as all schema/data.
"""

from alembic import context

from app.core.config import Settings
from app.db.models import metadata
from app.db.session import create_db_engine, initialize_storage

settings = Settings()

if context.is_offline_mode():
    raise RuntimeError("SQLite migrations require an online connection for integrity checks")

engine = create_db_engine(settings)
try:
    initialize_storage(settings, engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            if connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() != "ok":
                raise RuntimeError("Database integrity check failed before migration")
            if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
                raise RuntimeError("Database has foreign key violations before migration")
            context.configure(
                connection=connection,
                target_metadata=metadata,
                render_as_batch=True,
                transactional_ddl=True,
            )
            with context.begin_transaction():
                context.run_migrations()
            if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
                raise RuntimeError("Migration produced foreign key violations")
            if connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() != "ok":
                raise RuntimeError("Migration produced database corruption")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
finally:
    engine.dispose()
