from __future__ import annotations

import pytest

from app.hardware import (
    HardwareBusyError,
    HardwareFacade,
    HardwareOperationStatus,
    LockState,
    MockDrumAdapter,
    MockHardwareMode,
    MockLockAdapter,
    MockRfidAdapter,
)


def test_mock_drum_move_success_updates_position() -> None:
    drum = MockDrumAdapter(initial_position=1)

    result = drum.move_to_position(4)

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert result.position == 4
    assert drum.get_position().position == 4


def test_mock_drum_move_busy_mode_raises_error() -> None:
    drum = MockDrumAdapter(move_mode=MockHardwareMode.BUSY)

    with pytest.raises(HardwareBusyError, match="busy"):
        drum.move_to_position(2)


def test_mock_lock_unlock_success_changes_state() -> None:
    lock = MockLockAdapter(lock_states={(2, 7): LockState.LOCKED})

    result = lock.unlock_lock(2, 7)

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert result.lock_state is LockState.OPEN
    assert lock.get_lock_status(2, 7).lock_state is LockState.OPEN


def test_mock_rfid_reads_queued_cards_with_normalized_uid() -> None:
    reader = MockRfidAdapter()
    reader.queue_card("aa-bb cc")

    first_read = reader.read_card()
    second_read = reader.read_card()

    assert first_read.ok is True
    assert first_read.uid == "AABBCC"
    assert first_read.is_duplicate is False
    assert second_read.status is HardwareOperationStatus.NO_CARD
    assert second_read.uid is None


def test_hardware_facade_healthcheck_reports_ping_status() -> None:
    facade = HardwareFacade(
        drum_controller=MockDrumAdapter(),
        lock_controller=MockLockAdapter(ping_mode=MockHardwareMode.TIMEOUT),
        rfid_reader=MockRfidAdapter(),
    )

    snapshot = facade.hardware_healthcheck()

    assert snapshot.drum.is_available is True
    assert snapshot.lock.is_available is False
    assert snapshot.lock.status is HardwareOperationStatus.TIMEOUT
    assert snapshot.rfid.is_available is True
    assert snapshot.all_ok is False


def test_hardware_facade_combines_multiple_mocks() -> None:
    drum = MockDrumAdapter(initial_position=0)
    lock = MockLockAdapter(lock_states={(1, 3): LockState.LOCKED}, unlock_times={1: 5})
    rfid = MockRfidAdapter(emit_duplicates=True)
    rfid.queue_card("01 23 45")
    rfid.queue_card("01-23-45")
    facade = HardwareFacade(drum_controller=drum, lock_controller=lock, rfid_reader=rfid)

    move_result = facade.move_drum_to_position(6)
    unlock_result = facade.unlock_lock(1, 3)
    first_read = facade.read_rfid_card()
    duplicate_read = facade.read_rfid_card()
    unlock_time = facade.set_unlock_time(1, 9)

    assert move_result.position == 6
    assert unlock_result.lock_state is LockState.OPEN
    assert first_read.uid == "012345"
    assert first_read.is_duplicate is False
    assert duplicate_read.uid == "012345"
    assert duplicate_read.is_duplicate is True
    assert unlock_time.seconds == 9
