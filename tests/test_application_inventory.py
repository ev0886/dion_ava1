from __future__ import annotations

from app.application.inventory_service import InventoryService
from app.domain.enums import BindingType
from app.persistence.models import InventoryBalance, SlotItemBinding


class _FakeInventoryRepository:
    def __init__(self, balance: InventoryBalance | None, bindings: list[SlotItemBinding]) -> None:
        self._balance = balance
        self._bindings = bindings

    def get_balance(self, _slot_id: int, _item_id: int) -> InventoryBalance | None:
        return self._balance

    def list_bindings(self, *, slot_id: int | None = None, item_id: int | None = None) -> list[SlotItemBinding]:
        values = self._bindings
        if slot_id is not None:
            values = [binding for binding in values if binding.slot_id == slot_id]
        if item_id is not None:
            values = [binding for binding in values if binding.item_id == item_id]
        return values


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
    assert result.bindings[0].binding_id is None
