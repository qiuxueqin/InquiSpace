"""Establish the explicitly supported 20-table v1 migration boundary.

This revision is not an importer for old design-DDL databases. Unknown tables
are rejected rather than automatically stamped or overwritten. PRAGMA
user_version is not consulted or updated; alembic_version is authoritative.
"""

import sqlalchemy as sa
from alembic import op

from migrations.schema_snapshots import V1_TABLES, create_v1, indexes_v1

revision = "0002_business_v1"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names()) - {"alembic_version"}
    if existing:
        raise RuntimeError("Unrecognized legacy database; explicit reviewed import required")
    for table in V1_TABLES:
        create_v1(table)
    for table in V1_TABLES:
        indexes_v1(table)


def downgrade() -> None:
    # Explicitly destructive operator-requested downgrade to the empty scaffold.
    # env.py disables FKs outside the transaction to handle cyclic references.
    for table in reversed(V1_TABLES):
        op.drop_table(table)
