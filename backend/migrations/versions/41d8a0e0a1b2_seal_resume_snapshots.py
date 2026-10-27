"""Seal resume snapshots after initial bullets are inserted.

Revision ID: 41d8a0e0a1b2
Revises: c6251b97954d
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "41d8a0e0a1b2"
down_revision: str | None = "c6251b97954d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("resume_versions", sa.Column(
        "sealed", sa.Boolean(), nullable=False, server_default=sa.true()
    ))
    for table in ("resume_versions", "resume_bullets"):
        for action in ("UPDATE", "DELETE"):
            op.execute(f"DROP TRIGGER {table}_immutable_{action.lower()}")
    op.execute(
        "CREATE TRIGGER resume_versions_immutable_update BEFORE UPDATE ON resume_versions "
        "WHEN OLD.sealed = 1 BEGIN "
        "SELECT RAISE(ABORT, 'resume snapshots are immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER resume_versions_immutable_delete BEFORE DELETE ON resume_versions "
        "BEGIN SELECT RAISE(ABORT, 'resume snapshots are immutable'); END"
    )
    for action in ("INSERT", "UPDATE", "DELETE"):
        version_reference = "NEW.version_id" if action == "INSERT" else "OLD.version_id"
        op.execute(
            f"CREATE TRIGGER resume_bullets_immutable_{action.lower()} "
            f"BEFORE {action} ON resume_bullets "
            f"WHEN (SELECT sealed FROM resume_versions WHERE id = {version_reference}) = 1 "
            "BEGIN SELECT RAISE(ABORT, 'resume snapshots are immutable'); END"
        )


def downgrade() -> None:
    op.execute("DROP TRIGGER resume_bullets_immutable_insert")
    for table in ("resume_versions", "resume_bullets"):
        for action in ("UPDATE", "DELETE"):
            op.execute(f"DROP TRIGGER {table}_immutable_{action.lower()}")
            op.execute(
                f"CREATE TRIGGER {table}_immutable_{action.lower()} "
                f"BEFORE {action} ON {table} BEGIN "
                "SELECT RAISE(ABORT, 'resume snapshots are immutable'); END"
            )
    op.drop_column("resume_versions", "sealed")
