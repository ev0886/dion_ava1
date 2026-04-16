"""normalize user dispense restriction policy values

Revision ID: 20260410_0003
Revises: 20260410_0002
Create Date: 2026-04-10 12:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_0003"
down_revision = "20260410_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE users
            SET dispense_restriction_policy = CASE dispense_restriction_policy
                WHEN 'UNLIMITED' THEN 'unlimited'
                WHEN 'ONCE_PER_DAY' THEN 'once_per_day'
                ELSE dispense_restriction_policy
            END
            WHERE dispense_restriction_policy IN ('UNLIMITED', 'ONCE_PER_DAY')
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE users
            SET dispense_restriction_policy = CASE dispense_restriction_policy
                WHEN 'unlimited' THEN 'UNLIMITED'
                WHEN 'once_per_day' THEN 'ONCE_PER_DAY'
                ELSE dispense_restriction_policy
            END
            WHERE dispense_restriction_policy IN ('unlimited', 'once_per_day')
            """
        )
    )
