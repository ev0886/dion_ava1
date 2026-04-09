from __future__ import annotations

from datetime import datetime

from app.application.inventory_service import InventoryService
from app.domain.enums import BindingType
from app.persistence.repositories.inventory import AvailableDispenseOptionRecord
from app.persistence.models import InventoryBalance, SlotItemBinding


class _FakeScalarResult:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def scalars(self) -> "_FakeScalarResult":
        return self

    def __iter__(self):
        return iter(self._values)


class _FakeSession:
    def __init__(self, bindings: list[SlotItemBinding]) -> None:
        self._bindings = bindings

    def execute(self, _statement: object) -> _FakeScalarResult:
        return _FakeScalarResult(self._bindings)


class _FakeInventoryRepository:
    def __init__(self, balance: InventoryBalance | None, bindings: list[SlotItemBinding]) -> None:
        self._balance = balance
        self.session = _FakeSession(bindings)

    def get_balance(self, _slot_id: int, _item_id: int) -> InventoryBalance | None:
        return self._balance

    def list_available_dispense_options(self) -> tuple[AvailableDispenseOptionRecord, ...]:
        return (
            AvailableDispenseOptionRecord(
                slot_id=10,
                item_id=20,
                quantity=7,
                updated_at=datetime(2026, 4, 9, 12, 0, 0),
                slot_code="slot-p03-l01",
                drum_position=3,
                board_address=0,
                lock_number=1,
                item_sku="item-20",
                item_name="Item Twenty",
                item_unit="pcs",
            ),
        )


def test_inventory_lookup_result_shape() -> None:
    balance = InventoryBalance(slot_id=10, item_id=20, quantity=7)
    binding = SlotItemBinding(
        slot_id=10,
        item_id=20,
        binding_type=BindingType.PRIMARY,
        is_active=True,
        valid_from=None,
        valid_to=None,
    )
    service = InventoryService(_FakeInventoryRepository(balance, [binding]))

    result = service.lookup_inventory(slot_id=10, item_id=20)

    assert result.slot_id == 10
    assert result.item_id == 20
    assert result.balance is not None
    assert result.balance.quantity == 7
    assert len(result.bindings) == 1
    assert result.bindings[0].binding_type is BindingType.PRIMARY


def test_inventory_service_lists_available_dispense_options() -> None:
    service = InventoryService(_FakeInventoryRepository(balance=None, bindings=[]))

    result = service.list_available_dispense_options()

    assert len(result.options) == 1
    assert result.options[0].slot_id == 10
    assert result.options[0].item_id == 20
    assert result.options[0].quantity == 7
    assert result.options[0].board_address == 0
