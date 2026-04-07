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


def test_real_lock_adapter_ping_success_with_fake_transport() -> None:
    adapter = RealLockAdapter(config=_lock_config(), transport=_FakeTransport([bytes.fromhex("02 00 00 8F 10 02 03 BA 13 01")]))

    result = adapter.ping()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS


def test_real_lock_adapter_get_lock_status_uses_cu24_probe_but_reports_not_implemented() -> None:
    adapter = RealLockAdapter(config=_lock_config(), transport=_FakeTransport([bytes.fromhex("02 00 00 80 10 00 03 95")]))

    with pytest.raises(HardwareProtocolNotImplementedError, match="lock-state decoding is not implemented"):
        adapter.get_lock_status(0, 1)


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

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
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
