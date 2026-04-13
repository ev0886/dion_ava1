from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import BindingType, ItemStatus, SlotStatus
from app.persistence.models import InventoryBalance, Item, Slot, SlotItemBinding

DEMO_SEED_ITEM_ID = 1
DEMO_SEED_LOCK_NUMBER = 5
DEMO_SEED_DRUM_POSITIONS = (0, 3, 6, 9, 12, 15, 18, 21, 24, 27)
DEMO_SEED_SLOT_CODES = tuple(f"slot-p{position:02d}-l{DEMO_SEED_LOCK_NUMBER:02d}" for position in DEMO_SEED_DRUM_POSITIONS)


@dataclass(frozen=True, slots=True)
class DemoSeededSlotDTO:
    slot_id: int
    slot_code: str
    drum_position: int
    board_address: int
    lock_number: int
    quantity: int


@dataclass(frozen=True, slots=True)
class DemoInventorySeedResult:
    item_id: int
    slot_codes: tuple[str, ...]
    seeded_slots: tuple[DemoSeededSlotDTO, ...]


def seed_demo_multi_slot_inventory(session: Session, *, item_id: int = DEMO_SEED_ITEM_ID) -> DemoInventorySeedResult:
    item = session.get(Item, item_id)
    if item is None:
        raise ValueError(f"Item not found: {item_id}")
    if item.status is not ItemStatus.ACTIVE:
        raise ValueError(f"Item is not active: {item_id}")

    slots = _load_target_slots(session)
    seeded_slots: list[DemoSeededSlotDTO] = []
    for slot in slots:
        _ensure_primary_binding(session, slot_id=slot.id, item_id=item_id)
        _upsert_balance(session, slot_id=slot.id, item_id=item_id, quantity=1)
        seeded_slots.append(
            DemoSeededSlotDTO(
                slot_id=slot.id,
                slot_code=slot.code,
                drum_position=slot.drum_position,
                board_address=slot.board_address,
                lock_number=slot.lock_number,
                quantity=1,
            )
        )

    session.commit()
    return DemoInventorySeedResult(
        item_id=item_id,
        slot_codes=DEMO_SEED_SLOT_CODES,
        seeded_slots=tuple(seeded_slots),
    )


def _load_target_slots(session: Session) -> tuple[Slot, ...]:
    statement = (
        select(Slot)
        .where(Slot.code.in_(DEMO_SEED_SLOT_CODES))
        .order_by(Slot.drum_position.asc(), Slot.lock_number.asc(), Slot.id.asc())
    )
    slots = tuple(session.execute(statement).scalars())
    slots_by_code = {slot.code: slot for slot in slots}

    missing_codes = [code for code in DEMO_SEED_SLOT_CODES if code not in slots_by_code]
    if missing_codes:
        raise ValueError(f"Demo seed slots not found: {', '.join(missing_codes)}")

    resolved_slots: list[Slot] = []
    for code in DEMO_SEED_SLOT_CODES:
        slot = slots_by_code[code]
        if slot.status is not SlotStatus.ACTIVE:
            raise ValueError(f"Demo seed slot is not active: {slot.code}")
        if slot.board_address != 0:
            raise ValueError(f"Demo seed slot has incompatible board address: {slot.code} board_address={slot.board_address}")
        if slot.lock_number != DEMO_SEED_LOCK_NUMBER:
            raise ValueError(f"Demo seed slot has incompatible lock number: {slot.code} lock_number={slot.lock_number}")
        resolved_slots.append(slot)

    return tuple(resolved_slots)


def _ensure_primary_binding(session: Session, *, slot_id: int, item_id: int) -> None:
    statement = select(SlotItemBinding).where(
        SlotItemBinding.slot_id == slot_id,
        SlotItemBinding.item_id == item_id,
        SlotItemBinding.binding_type == BindingType.PRIMARY,
    )
    binding = session.execute(statement).scalar_one_or_none()
    if binding is None:
        session.add(
            SlotItemBinding(
                slot_id=slot_id,
                item_id=item_id,
                binding_type=BindingType.PRIMARY,
                is_active=True,
                valid_from=None,
                valid_to=None,
            )
        )
        return

    binding.is_active = True


def _upsert_balance(session: Session, *, slot_id: int, item_id: int, quantity: int) -> None:
    statement = select(InventoryBalance).where(
        InventoryBalance.slot_id == slot_id,
        InventoryBalance.item_id == item_id,
    )
    balance = session.execute(statement).scalar_one_or_none()
    if balance is None:
        session.add(InventoryBalance(slot_id=slot_id, item_id=item_id, quantity=quantity))
        return

    balance.quantity = quantity
