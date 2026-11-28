"""add_stored_files_table

Revision ID: f3a9d1c2e4b0
Revises: dbbe0ed386ce
Create Date: 2026-11-28 10:48:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f3a9d1c2e4b0"
down_revision = "dbbe0ed386ce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stored_files",
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("content_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("storage_key"),
    )


def downgrade() -> None:
    op.drop_table("stored_files")
