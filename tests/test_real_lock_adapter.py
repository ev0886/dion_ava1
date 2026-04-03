from __future__ import annotations

import pytest

from app.config import AppSettings, HardwareProvider
from app.hardware import (
    HardwareFailureError,
    HardwareOperationStatus,
    HardwareTimeoutError,
    HardwareUnavailableError,
    LockState,
    RealLockAdapter,
    create_hardware_bundle,
)


def test_real_lock_adapter_ping_success_with_fake_transport() -> None:
    adapter = RealLockAdapter(config=_lock_config(), transport=_FakeTransport([b"PONG\n"]))

    result = adapter.ping()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS


@pytest.mark.parametrize(
    ("response", "expected_state", "expected_ok"),
    [
        (b"STATUS:LOCKED\n", LockState.LOCKED, True),
        (b"STATUS:OPEN\n", LockState.OPEN, True),
        (b"STATUS:UNAVAILABLE\n", LockState.UNAVAILABLE, False),
    ],
)
def test_real_lock_adapter_get_lock_status_success(
    response: bytes,
    expected_state: LockState,
    expected_ok: bool,
) -> None:
    adapter = RealLockAdapter(config=_lock_config(), transport=_FakeTransport([response]))

    result = adapter.get_lock_status(2, 7)

    assert result.lock_state is expected_state
    assert result.ok is expected_ok


def test_real_lock_adapter_unlock_success_path() -> None:
    adapter = RealLockAdapter(config=_lock_config(), transport=_FakeTransport([b"UNLOCKED\n"]))

    result = adapter.unlock_lock(1, 3)

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert result.lock_state is LockState.OPEN


def test_real_lock_adapter_unlock_already_open_path() -> None:
    adapter = RealLockAdapter(config=_lock_config(), transport=_FakeTransport([b"ALREADY_OPEN\n"]))

    result = adapter.unlock_lock(1, 3)

    assert result.ok is True
    assert result.status is HardwareOperationStatus.ALREADY_OPEN
    assert result.lock_state is LockState.OPEN


def test_real_lock_adapter_get_unlock_time_success() -> None:
    adapter = RealLockAdapter(config=_lock_config(), transport=_FakeTransport([b"UNLOCK_TIME:9\n"]))

    result = adapter.get_unlock_time(1)

    assert result.ok is True
    assert result.seconds == 9


def test_real_lock_adapter_set_unlock_time_success() -> None:
    adapter = RealLockAdapter(config=_lock_config(), transport=_FakeTransport([b"SET_UNLOCK_TIME:11\n"]))

    result = adapter.set_unlock_time(1, 11)

    assert result.ok is True
    assert result.seconds == 11


def test_real_lock_adapter_malformed_response_raises_safe_failure() -> None:
    adapter = RealLockAdapter(config=_lock_config(), transport=_FakeTransport([123]))  # type: ignore[list-item]

    with pytest.raises(HardwareFailureError, match="malformed response"):
        adapter.get_lock_status(1, 1)


def test_real_lock_adapter_transport_timeout_and_error_handling_stays_safe() -> None:
    timeout_adapter = RealLockAdapter(config=_lock_config(), transport=_RaisingTransport(TimeoutError("timed out")))
    error_adapter = RealLockAdapter(config=_lock_config(), transport=_RaisingTransport(OSError("connect failed")))

    with pytest.raises(HardwareTimeoutError) as timeout_error:
        timeout_adapter.ping()
    with pytest.raises(HardwareUnavailableError) as unavailable_error:
        error_adapter.ping()

    assert timeout_error.value.normalized_status is HardwareOperationStatus.TIMEOUT
    assert timeout_error.value.detail["kind"] == "timeout"
    assert unavailable_error.value.normalized_status is HardwareOperationStatus.UNAVAILABLE
    assert unavailable_error.value.detail["kind"] == "io_error"


def test_real_provider_composition_still_works_with_operational_lock_transport() -> None:
    settings = AppSettings(
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _tcp_endpoint_config(code="lock-1", driver_name="lock-driver", host="127.0.0.1", port=9001),
            "rfid_reader": _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM3"),
        },
    )

    bundle = create_hardware_bundle(
        settings,
        transport_overrides={"lock_controller": _FakeTransport([b"PONG\n", b"STATUS:LOCKED\n", b"UNLOCK_TIME:7\n"])},
    )

    ping_result = bundle.lock_controller.ping()
    status_result = bundle.lock_controller.get_lock_status(1, 2)
    unlock_time = bundle.lock_controller.get_unlock_time(1)

    assert bundle.provider is HardwareProvider.REAL
    assert ping_result.ok is True
    assert status_result.lock_state is LockState.LOCKED
    assert unlock_time.seconds == 7


class _FakeTransport:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        if not self._responses:
            raise AssertionError("No fake responses remain.")
        response = self._responses.pop(0)
        return response  # type: ignore[return-value]


class _RaisingTransport:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        raise self._error


def _lock_config():
    from app.hardware.transport_config import HardwareEndpointTransportConfig

    return HardwareEndpointTransportConfig.model_validate(
        _tcp_endpoint_config(code="lock-1", driver_name="lock-driver", host="127.0.0.1", port=9001)
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


def _tcp_endpoint_config(*, code: str, driver_name: str, host: str, port: int) -> dict[str, object]:
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
            "transport": "tcp",
            "host": host,
            "port": port,
        },
    }
