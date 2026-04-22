from __future__ import annotations

import pytest

from app.config import AppSettings, HardwareProvider
from app.hardware import (
    HardwareFailureError,
    HardwareOperationStatus,
    HardwareProtocolNotImplementedError,
    HardwareTimeoutError,
    HardwareUnavailableError,
    LockState,
    RealLockAdapter,
    create_hardware_bundle,
)
from app.hardware.lock_cu24 import build_packet


def test_real_lock_adapter_ping_success_with_fake_transport() -> None:
    adapter = RealLockAdapter(config=_lock_config(), transport=_FakeTransport([bytes.fromhex("02 00 00 8F 10 02 03 BA 13 01")]))

    result = adapter.ping()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS


def test_real_lock_adapter_get_board_status_decodes_cu24_hook_mask() -> None:
    transport = _FakeTransport([_status_response(data=bytes.fromhex("FF 7F 00"))])
    adapter = RealLockAdapter(config=_lock_config(), transport=transport)

    result = adapter.get_board_status(0)

    assert transport.requests == [build_packet(address=0, lock_number=0, command=0x80)]
    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert result.raw_hook_mask == 0x007FFF
    assert all(state is LockState.LOCKED for state in result.lock_states[:15])
    assert all(state is LockState.OPEN for state in result.lock_states[15:])
    assert result.any_open() is True
    assert result.is_lock_closed(1) is True
    assert result.is_lock_closed(15) is True
    assert result.is_lock_open(16) is True
    assert result.is_lock_open(24) is True


def test_real_lock_adapter_get_lock_status_uses_board_wide_status_and_maps_physical_lock_numbers() -> None:
    transport = _FakeTransport([_status_response(data=bytes.fromhex("FE 7F 00"))])
    adapter = RealLockAdapter(config=_lock_config(), transport=transport)

    closed_result = adapter.get_lock_status(0, 1)

    assert transport.requests == [build_packet(address=0, lock_number=0, command=0x80)]
    assert closed_result.lock_state is LockState.OPEN


def test_real_lock_adapter_get_lock_status_reports_closed_when_requested_bit_is_set() -> None:
    adapter = RealLockAdapter(config=_lock_config(), transport=_FakeTransport([_status_response(data=bytes.fromhex("FF 7F 00"))]))

    result = adapter.get_lock_status(0, 15)

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert result.lock_number == 15
    assert result.lock_state is LockState.LOCKED


def test_real_lock_adapter_unlock_success_path() -> None:
    adapter = RealLockAdapter(config=_lock_config(), transport=_FakeTransport([bytes.fromhex("02 00 00 81 10 00 03 96")]))

    result = adapter.unlock_lock(0, 1)

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert result.lock_state is LockState.OPEN


def test_real_lock_adapter_unlock_with_non_configured_board_address_fails() -> None:
    adapter = RealLockAdapter(config=_lock_config(), transport=_FakeTransport([]))

    with pytest.raises(HardwareFailureError, match="configured for board address 0, got 1"):
        adapter.unlock_lock(1, 1)


def test_real_lock_adapter_unlock_time_methods_report_not_implemented() -> None:
    adapter = RealLockAdapter(config=_lock_config(), transport=_FakeTransport([]))

    with pytest.raises(HardwareProtocolNotImplementedError, match="unlock-time reads"):
        adapter.get_unlock_time(0)
    with pytest.raises(HardwareProtocolNotImplementedError, match="unlock-time writes"):
        adapter.set_unlock_time(0, 11)


def test_real_lock_adapter_malformed_response_raises_safe_failure() -> None:
    adapter = RealLockAdapter(config=_lock_config(), transport=_FakeTransport([123]))  # type: ignore[list-item]

    with pytest.raises(HardwareFailureError, match="malformed response"):
        adapter.get_lock_status(0, 1)


def test_real_lock_adapter_rejects_non_board_wide_status_payload_length() -> None:
    adapter = RealLockAdapter(config=_lock_config(), transport=_FakeTransport([_status_response(data=bytes.fromhex("FF 7F"))]))

    with pytest.raises(HardwareFailureError, match="payload length: 2 bytes"):
        adapter.get_board_status(0)


def test_real_lock_adapter_transport_timeout_and_error_handling_stays_safe() -> None:
    timeout_adapter = RealLockAdapter(config=_lock_config(), transport=_RaisingTransport(TimeoutError("timed out")))
    error_adapter = RealLockAdapter(config=_lock_config(), transport=_RaisingTransport(OSError("connect failed")))

    with pytest.raises(HardwareTimeoutError, match="timed out"):
        timeout_adapter.ping()
    with pytest.raises(HardwareUnavailableError, match="connect failed"):
        error_adapter.ping()


def test_real_provider_composition_still_works_with_operational_lock_transport() -> None:
    settings = AppSettings(
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _lock_serial_endpoint_config(code="lock-1", driver_name="lock-driver", port="COM2"),
            "rfid_reader": _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM3"),
        },
    )

    bundle = create_hardware_bundle(
        settings,
        transport_overrides={
            "lock_controller": _FakeTransport(
                [bytes.fromhex("02 00 00 8F 10 02 03 BA 13 01"), bytes.fromhex("02 00 01 81 10 00 03 97")]
            )
        },
    )

    ping_result = bundle.lock_controller.ping()
    unlock_result = bundle.lock_controller.unlock_lock(0, 2)

    assert bundle.provider is HardwareProvider.REAL
    assert ping_result.ok is True
    assert unlock_result.lock_number == 2
    assert unlock_result.lock_state is LockState.OPEN


def test_real_lock_adapter_ping_rejects_truncated_cu24_version_payload() -> None:
    adapter = RealLockAdapter(config=_lock_config(), transport=_FakeTransport([bytes.fromhex("02 00 00 8F 10 02 03 BA 13")]))

    with pytest.raises(HardwareFailureError, match="data length mismatch"):
        adapter.ping()


class _FakeTransport:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.requests: list[bytes] = []

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        self.requests.append(payload)
        if not self._responses:
            raise AssertionError("No fake responses remain.")
        response = self._responses.pop(0)
        return response  # type: ignore[return-value]

    def send(self, payload: bytes) -> None:
        return None


class _RaisingTransport:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        raise self._error

    def send(self, payload: bytes) -> None:
        raise self._error


def _lock_config():
    from app.hardware.transport_config import LockHardwareEndpointTransportConfig

    return LockHardwareEndpointTransportConfig.model_validate(
        _lock_serial_endpoint_config(code="lock-1", driver_name="lock-driver", port="COM7")
    )


def _status_response(*, data: bytes, board_address: int = 0, lock_number: int = 0) -> bytes:
    header = bytes((0x02, board_address, lock_number, 0x80, 0x10, len(data), 0x03))
    checksum = (sum(header) + sum(data)) & 0xFF
    return header + bytes((checksum,)) + data


def _serial_endpoint_config(*, code: str, driver_name: str, port: str) -> dict[str, object]:
    return {
        "endpoint": {
            "code": code,
            "driver_name": driver_name,
            "enabled": True,
            "timeouts": {
                "connect_timeout_ms": 1000,
                "read_timeout_ms": 1000,
                "write_timeout_ms": 1000,
            },
        },
        "transport": {
            "transport": "serial",
            "port": port,
            "baudrate": 9600,
            "data_bits": 8,
            "parity": "none",
            "stop_bits": 1,
        },
    }


def _lock_serial_endpoint_config(*, code: str, driver_name: str, port: str, board_address: int = 0) -> dict[str, object]:
    return {
        "endpoint": {
            "code": code,
            "driver_name": driver_name,
            "enabled": True,
            "timeouts": {
                "connect_timeout_ms": 1000,
                "read_timeout_ms": 1000,
                "write_timeout_ms": 1000,
            },
        },
        "protocol": {
            "board_address": board_address,
        },
        "transport": {
            "transport": "serial",
            "port": port,
            "baudrate": 19200,
            "data_bits": 8,
            "parity": "none",
            "stop_bits": 1,
        },
    }
