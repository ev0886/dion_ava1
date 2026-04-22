"""backfill active inventory items for nomenclature entries

Revision ID: 20260422_0006
Revises: 20260421_0005
Create Date: 2026-04-22 09:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.domain.enums import ItemStatus
from app.persistence.models import Item

revision = "20260422_0006"
down_revision = "20260421_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "nomenclature_entries" not in table_names or "items" not in table_names:
        return
    active_item_status = _persisted_item_status(bind, ItemStatus.ACTIVE)

    nomenclature_rows = bind.execute(
        sa.text(
            """
            SELECT id, name, normalized_name
            FROM nomenclature_entries
            WHERE is_active = 1
            ORDER BY id ASC
            """
        )
    ).mappings()
    item_rows = bind.execute(
        sa.text(
            """
            SELECT sku, name, status
            FROM items
            ORDER BY id ASC
            """
        )
    ).mappings()

    active_item_names = {
        _normalize_name(row["name"])
        for row in item_rows
        if row["status"] == active_item_status
    }
    existing_skus = {row["sku"] for row in item_rows}

    for row in nomenclature_rows:
        if row["normalized_name"] in active_item_names:
            continue

        sync_sku = f"nomenclature-{row['id']}"
        if sync_sku in existing_skus:
            continue

        bind.execute(
            sa.text(
                """
                INSERT INTO items (item_group_id, sku, name, description, unit, return_allowed, min_level, status)
                VALUES (NULL, :sku, :name, NULL, 'pcs', 1, 0, :status)
                """
            ),
            {
                "sku": sync_sku,
                "name": row["name"],
                "status": active_item_status,
            },
        )
        active_item_names.add(row["normalized_name"])
        existing_skus.add(sync_sku)


def downgrade() -> None:
    # Backfilled inventory rows may already be referenced by bindings, balances,
    # permissions, and operations, so this data migration is intentionally irreversible.
    return


def _normalize_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _persisted_item_status(bind: sa.Connection, status: ItemStatus) -> str:
    processor = Item.__table__.c.status.type.bind_processor(bind.dialect)
    if processor is None:
        raise RuntimeError("Item.status column does not expose a bind processor")
    persisted = processor(status)
    if persisted is None:
        raise RuntimeError(f"Unable to derive persisted Item.status for {status!r}")
    return persisted
