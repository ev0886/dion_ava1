from __future__ import annotations

from collections.abc import Iterable

from app.application.exceptions import InvalidStateTransitionError
from app.domain.enums import OperationState, OperationType

_COMMON_FALLBACKS: tuple[OperationState, ...] = (
    OperationState.FAILED,
    OperationState.RECOVERY_REQUIRED,
)

_OPERATION_SEQUENCES: dict[OperationType, tuple[OperationState, ...]] = {
    OperationType.DISPENSE: (
        OperationState.CREATED,
        OperationState.AUTHORIZED,
        OperationState.VALIDATION_IN_PROGRESS,
        OperationState.VALIDATED,
        OperationState.QUEUED_FOR_EXECUTION,
        OperationState.POSITIONING_REQUESTED,
        OperationState.POSITIONING_ACKNOWLEDGED,
        OperationState.POSITIONING_IN_PROGRESS,
        OperationState.POSITIONING_COMPLETED,
        OperationState.UNLOCK_REQUESTED,
        OperationState.UNLOCK_ACKNOWLEDGED,
        OperationState.UNLOCK_COMPLETED,
        OperationState.USER_ACTION_PENDING,
        OperationState.COMPLETION_VERIFICATION,
        OperationState.INVENTORY_WRITE_PENDING,
        OperationState.INVENTORY_WRITTEN,
        OperationState.COMPLETED,
    ),
    OperationType.RETURN: (
        OperationState.CREATED,
        OperationState.AUTHORIZED,
        OperationState.RETURN_RULES_VALIDATION,
        OperationState.RETURN_SLOT_RESOLUTION_IN_PROGRESS,
        OperationState.RETURN_SLOT_RESOLVED,
        OperationState.VALIDATED,
        OperationState.QUEUED_FOR_EXECUTION,
        OperationState.POSITIONING_REQUESTED,
        OperationState.POSITIONING_ACKNOWLEDGED,
        OperationState.POSITIONING_IN_PROGRESS,
        OperationState.POSITIONING_COMPLETED,
        OperationState.UNLOCK_REQUESTED,
        OperationState.UNLOCK_ACKNOWLEDGED,
        OperationState.UNLOCK_COMPLETED,
        OperationState.USER_ACTION_PENDING,
        OperationState.COMPLETION_VERIFICATION,
        OperationState.INVENTORY_WRITE_PENDING,
        OperationState.INVENTORY_WRITTEN,
        OperationState.COMPLETED,
    ),
    OperationType.REFILL_ITEM: (
        OperationState.CREATED,
        OperationState.AUTHORIZED,
        OperationState.SERVICE_MODE_REQUESTED,
        OperationState.SERVICE_MODE_ACTIVE,
        OperationState.AWAITING_SLOT_SELECTION,
        OperationState.SLOT_SELECTED,
        OperationState.POSITIONING_REQUESTED,
        OperationState.POSITIONING_ACKNOWLEDGED,
        OperationState.POSITIONING_IN_PROGRESS,
        OperationState.POSITIONING_COMPLETED,
        OperationState.AWAITING_QTY_INPUT,
        OperationState.QTY_ENTERED,
        OperationState.BALANCE_UPDATE_PENDING,
        OperationState.BALANCE_UPDATED,
        OperationState.AWAITING_NEXT_ACTION,
        OperationState.SESSION_COMPLETION_REQUESTED,
        OperationState.SESSION_FINALIZATION_IN_PROGRESS,
        OperationState.SESSION_COMPLETED,
    ),
    OperationType.RECOVERY: (
        OperationState.STARTUP_SCAN,
        OperationState.RECOVERY_TARGETS_FOUND,
        OperationState.HARDWARE_STATE_REQUESTED,
        OperationState.RECOVERY_EVALUATION_IN_PROGRESS,
        OperationState.OPERATION_RECONCILIATION_IN_PROGRESS,
        OperationState.MANUAL_CONFIRMATION_REQUIRED,
        OperationState.MANUAL_RECONCILIATION_IN_PROGRESS,
        OperationState.RECOVERY_ACTIONS_COMMIT_PENDING,
        OperationState.RECOVERY_ACTIONS_COMMITTED,
        OperationState.POST_RECOVERY_SAFETY_CHECK,
        OperationState.DEGRADED_READY,
        OperationState.SYSTEM_READY,
        OperationState.FAILED,
    ),
}

_TERMINAL_BY_OPERATION: dict[OperationType, tuple[OperationState, ...]] = {
    OperationType.DISPENSE: (
        OperationState.COMPLETED,
        OperationState.REJECTED,
        OperationState.CANCELLED,
        OperationState.TIMED_OUT,
        OperationState.FAILED,
        OperationState.RECOVERY_REQUIRED,
    ),
    OperationType.RETURN: (
        OperationState.COMPLETED,
        OperationState.REJECTED,
        OperationState.CANCELLED,
        OperationState.TIMED_OUT,
        OperationState.FAILED,
        OperationState.RECOVERY_REQUIRED,
    ),
    OperationType.REFILL_ITEM: (
        OperationState.SESSION_COMPLETED,
        OperationState.CANCELLED,
        OperationState.FAILED,
        OperationState.RECOVERY_REQUIRED,
    ),
    OperationType.RECOVERY: (
        OperationState.DEGRADED_READY,
        OperationState.SYSTEM_READY,
        OperationState.FAILED,
    ),
}


def get_allowed_target_states(
    operation_type: OperationType,
    current_state: OperationState,
) -> tuple[OperationState, ...]:
    sequence = _OPERATION_SEQUENCES[operation_type]
    if current_state in _TERMINAL_BY_OPERATION[operation_type]:
        return ()

    allowed: list[OperationState] = []
    for index, state in enumerate(sequence):
        if state != current_state:
            continue
        if index + 1 < len(sequence):
            allowed.append(sequence[index + 1])
        break

    allowed.extend(state for state in _COMMON_FALLBACKS if state not in allowed)

    if operation_type is OperationType.REFILL_ITEM and current_state is OperationState.AWAITING_NEXT_ACTION:
        allowed.append(OperationState.AWAITING_SLOT_SELECTION)

    if operation_type is OperationType.RECOVERY and current_state is OperationState.MANUAL_CONFIRMATION_REQUIRED:
        allowed.append(OperationState.RECOVERY_ACTIONS_COMMIT_PENDING)

    return tuple(allowed)


def can_transition(
    operation_type: OperationType,
    current_state: OperationState,
    target_state: OperationState,
) -> bool:
    return target_state in get_allowed_target_states(operation_type, current_state)


def assert_transition_allowed(
    operation_type: OperationType,
    current_state: OperationState,
    target_state: OperationState,
) -> None:
    if can_transition(operation_type, current_state, target_state):
        return

    allowed_targets = ", ".join(state.value for state in get_allowed_target_states(operation_type, current_state))
    raise InvalidStateTransitionError(
        f"Invalid transition for {operation_type.value}: {current_state.value} -> "
        f"{target_state.value}. Allowed: [{allowed_targets}]"
    )


def assert_transition_path(
    operation_type: OperationType,
    states: Iterable[OperationState],
) -> None:
    iterator = iter(states)
    try:
        current_state = next(iterator)
    except StopIteration:
        return

    for target_state in iterator:
        assert_transition_allowed(operation_type, current_state, target_state)
        current_state = target_state
