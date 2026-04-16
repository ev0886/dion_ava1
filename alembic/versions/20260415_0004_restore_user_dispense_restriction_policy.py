"""restore user dispense restriction policy for admin workflows

Revision ID: 20260415_0004
Revises: 20260410_0003
Create Date: 2026-04-15 14:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260415_0004"
down_revision = "20260410_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "dispense_restriction_policy" in columns:
        return

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "dispense_restriction_policy",
                sa.String(length=12),
                nullable=False,
                server_default="unlimited",
            )
        )

    op.execute(
        sa.text(
            "UPDATE users SET dispense_restriction_policy = 'unlimited' "
            "WHERE dispense_restriction_policy IS NULL OR dispense_restriction_policy = ''"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "dispense_restriction_policy" not in columns:
        return

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("dispense_restriction_policy")
