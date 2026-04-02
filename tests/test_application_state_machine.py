from __future__ import annotations

import pytest

from app.application.exceptions import InvalidStateTransitionError
from app.application.state_machine import assert_transition_allowed
from app.domain.enums import OperationState, OperationType


def test_invalid_state_transition_detected() -> None:
    with pytest.raises(InvalidStateTransitionError, match="created -> unlock_requested"):
        assert_transition_allowed(
            OperationType.DISPENSE,
            OperationState.CREATED,
            OperationState.UNLOCK_REQUESTED,
        )
