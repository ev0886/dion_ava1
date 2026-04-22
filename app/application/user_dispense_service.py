from __future__ import annotations

from dataclasses import dataclass

from app.application.dispense_service import DispenseOperationService
from app.application.dto.inventory import UserDispenseOptionDTO, UserDispenseOptionsResult
from app.application.dto.operations import DispenseRequest, OperationDTO
from app.application.exceptions import ValidationError
from app.hardware import HardwareFacade
from app.persistence.repositories.inventory import InventoryRepository


@dataclass(slots=True)
class UserDispenseService:
    inventory_repository: InventoryRepository
    dispense_service: DispenseOperationService
    hardware_facade: HardwareFacade

    def list_options_for_user(self, user_id: int) -> UserDispenseOptionsResult:
        self._validate_user_id(user_id)

        try:
            self.dispense_service._enforce_dispense_restriction(user_id)
        except ValidationError as error:
            return UserDispenseOptionsResult(
                options=(),
                restriction_blocked=True,
                unavailable_reason=str(error),
            )

        aggregated: dict[int, UserDispenseOptionDTO] = {}
        for option in self.inventory_repository.list_available_dispense_options():
            current = aggregated.get(option.item_id)
            if current is None:
                aggregated[option.item_id] = UserDispenseOptionDTO(
                    item_id=option.item_id,
                    item_name=option.item_name,
                    item_unit=option.item_unit,
                    total_quantity=option.quantity,
                )
                continue
            aggregated[option.item_id] = UserDispenseOptionDTO(
                item_id=current.item_id,
                item_name=current.item_name,
                item_unit=current.item_unit,
                total_quantity=current.total_quantity + option.quantity,
            )

        return UserDispenseOptionsResult(options=tuple(aggregated.values()))

    def dispense(self, request: DispenseRequest) -> OperationDTO:
        self._validate_request(request)
        return self.dispense_service.execute(
            DispenseRequest(
                user_id=request.user_id,
                item_id=request.item_id,
                slot_id=None,
                quantity=request.quantity,
                session_id=request.session_id,
            ),
            self.hardware_facade,
        )

    @staticmethod
    def _validate_request(request: DispenseRequest) -> None:
        if request.user_id <= 0:
            raise ValidationError("user_id must be positive")
        if request.item_id <= 0:
            raise ValidationError("item_id must be positive")
        if request.quantity != 1:
            raise ValidationError("quantity must be exactly 1 for user dispense")

    @staticmethod
    def _validate_user_id(user_id: int) -> None:
        if user_id <= 0:
            raise ValidationError("user_id must be positive")
