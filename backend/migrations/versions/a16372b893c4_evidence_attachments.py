"""Immutable supporting text attachment registry.

Revision ID: a16372b893c4
Revises: 5771a0773bcb
"""

import sqlalchemy as sa
from alembic import op

revision = "a16372b893c4"
down_revision = "5771a0773bcb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "evidence_id",
            sa.String(36),
            sa.ForeignKey("evidence_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("relative_path", sa.String(1000), nullable=False, unique=True),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(80), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("evidence_id", "checksum"),
        sa.CheckConstraint("size > 0 AND size <= 1048576", name="attachment_size"),
    )
    # Files and their registry entries are append-only; approved snapshots may reference them.
    for operation in ("UPDATE", "DELETE"):
        op.execute(
            f"CREATE TRIGGER attachments_no_{operation.lower()} BEFORE {operation} ON attachments "
            "BEGIN SELECT RAISE(ABORT, 'attachments are immutable'); END"
        )


def downgrade() -> None:
    op.execute("DROP TRIGGER attachments_no_update")
    op.execute("DROP TRIGGER attachments_no_delete")
    op.drop_table("attachments")
