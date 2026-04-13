from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.bootstrap import bootstrap
from app.config import AppSettings, HardwareProvider
from app.demo_inventory_seed import (
    DEMO_SEED_DRUM_POSITIONS,
    DEMO_SEED_ITEM_ID,
    DEMO_SEED_LOCK_NUMBER,
    DEMO_SEED_SLOT_CODES,
    seed_demo_multi_slot_inventory,
)
from app.domain.enums import BindingType, ItemStatus
from app.persistence.models import InventoryBalance, Item, Slot, SlotItemBinding


def test_seed_demo_multi_slot_inventory_upserts_targeted_real_runtime_slots(tmp_path: Path) -> None:
    settings = _real_settings(tmp_path, "demo_seed.sqlite3")
    bootstrap(settings)

    engine = create_engine(settings.database_url, future=True, connect_args={"check_same_thread": False})
    try:
        with Session(engine) as session:
            session.add(
                Item(
                    id=DEMO_SEED_ITEM_ID,
                    item_group_id=None,
                    sku="item-1",
                    name="Item One",
                    description=None,
                    unit="pcs",
                    return_allowed=True,
                    min_level=0,
                    status=ItemStatus.ACTIVE,
                )
            )
            session.commit()

            slot_140 = session.execute(select(Slot).where(Slot.code == "slot-p09-l05")).scalar_one()
            session.add(
                SlotItemBinding(
                    slot_id=slot_140.id,
                    item_id=DEMO_SEED_ITEM_ID,
                    binding_type=BindingType.PRIMARY,
                    is_active=False,
                    valid_from=None,
                    valid_to=None,
                )
            )
            session.add(InventoryBalance(slot_id=slot_140.id, item_id=DEMO_SEED_ITEM_ID, quantity=7))
            session.commit()

            result = seed_demo_multi_slot_inventory(session)

            balances = session.execute(
                select(InventoryBalance)
                .where(InventoryBalance.item_id == DEMO_SEED_ITEM_ID)
                .order_by(InventoryBalance.slot_id.asc())
            ).scalars().all()
            bindings = session.execute(
                select(SlotItemBinding)
                .where(
                    SlotItemBinding.item_id == DEMO_SEED_ITEM_ID,
                    SlotItemBinding.binding_type == BindingType.PRIMARY,
                )
                .order_by(SlotItemBinding.slot_id.asc())
            ).scalars().all()
    finally:
        engine.dispose()

    assert result.item_id == DEMO_SEED_ITEM_ID
    assert result.slot_codes == DEMO_SEED_SLOT_CODES
    assert [slot.drum_position for slot in result.seeded_slots] == list(DEMO_SEED_DRUM_POSITIONS)
    assert all(slot.lock_number == DEMO_SEED_LOCK_NUMBER for slot in result.seeded_slots)
    assert all(slot.board_address == 0 for slot in result.seeded_slots)
    assert len(result.seeded_slots) == 10
    assert any(slot.slot_id == 140 and slot.slot_code == "slot-p09-l05" for slot in result.seeded_slots)
    assert [balance.slot_id for balance in balances] == [5, 50, 95, 140, 185, 230, 275, 320, 365, 410]
    assert all(balance.quantity == 1 for balance in balances)
    assert [binding.slot_id for binding in bindings] == [5, 50, 95, 140, 185, 230, 275, 320, 365, 410]
    assert all(binding.is_active for binding in bindings)


def test_seed_demo_multi_slot_inventory_rejects_missing_runtime_slots(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="demo_seed_missing_slots.sqlite3",
        alembic_config_path=Path("alembic.ini"),
    )
    bootstrap(settings)

    engine = create_engine(settings.database_url, future=True, connect_args={"check_same_thread": False})
    try:
        with Session(engine) as session:
            session.add(
                Item(
                    id=DEMO_SEED_ITEM_ID,
                    item_group_id=None,
                    sku="item-1",
                    name="Item One",
                    description=None,
                    unit="pcs",
                    return_allowed=True,
                    min_level=0,
                    status=ItemStatus.ACTIVE,
                )
            )
            session.commit()

            with pytest.raises(ValueError, match="Demo seed slots not found"):
                seed_demo_multi_slot_inventory(session)
    finally:
        engine.dispose()


def _real_settings(tmp_path: Path, sqlite_filename: str) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "lock_controller": {
                "endpoint": {
                    "code": "lock-1",
                    "driver_name": "lock-driver",
                    "enabled": True,
                    "timeouts": {
                        "connect_timeout_ms": 1000,
                        "read_timeout_ms": 1000,
                        "write_timeout_ms": 1000,
                    },
                },
                "protocol": {"board_address": 0},
                "transport": {
                    "transport": "serial",
                    "port": "COM2",
                    "baudrate": 19200,
                    "data_bits": 8,
                    "parity": "none",
                    "stop_bits": 1,
                },
            }
        },
    )
