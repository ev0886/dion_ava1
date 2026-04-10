"""add user dispense restriction policy

Revision ID: 20260410_0002
Revises: 20260401_0001
Create Date: 2026-04-10 11:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_0002"
down_revision = "20260401_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "dispense_restriction_policy",
            sa.String(length=12),
            nullable=False,
            server_default=sa.text("'unlimited'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "dispense_restriction_policy")
