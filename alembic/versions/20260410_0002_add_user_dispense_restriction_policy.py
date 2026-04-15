"""compatibility placeholder for removed dispense restriction policy migration

Revision ID: 20260410_0002
Revises: 20260401_0001
Create Date: 2026-04-10 11:45:00
"""

from __future__ import annotations


revision = "20260410_0002"
down_revision = "20260401_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve historical Alembic ancestry for databases stamped on older branch history.
    pass


def downgrade() -> None:
    pass
