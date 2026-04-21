"""add admin nomenclature directory

Revision ID: 20260421_0005
Revises: 20260415_0004
Create Date: 2026-04-21 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260421_0005"
down_revision = "20260415_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "nomenclature_entries" in set(inspector.get_table_names()):
        return

    op.create_table(
        "nomenclature_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("normalized_name", name="uq_nomenclature_entries_normalized_name"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "nomenclature_entries" not in set(inspector.get_table_names()):
        return

    op.drop_table("nomenclature_entries")
