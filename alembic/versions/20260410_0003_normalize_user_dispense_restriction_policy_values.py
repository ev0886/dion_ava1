"""compatibility placeholder for removed dispense restriction policy normalization

Revision ID: 20260410_0003
Revises: 20260410_0002
Create Date: 2026-04-10 12:40:00
"""

from __future__ import annotations


revision = "20260410_0003"
down_revision = "20260410_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve historical Alembic ancestry for databases stamped on older branch history.
    pass


def downgrade() -> None:
    pass
