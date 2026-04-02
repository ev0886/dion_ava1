from __future__ import annotations

import pytest

from app.config import AppSettings, HardwareProvider
from app.hardware import (
    DrumPositionResult,
    HardwareFailureError,
    HardwareOperationStatus,
    HardwareTimeoutError,
    HardwareUnavailableError,
    RealDrumAdapter,
    create_hardware_bundle,
)


def test_real_drum_adapter_ping_success_with_fake_transport() -> None:
    adapter = RealDrumAdapter(config=_drum_config(), transport=_FakeTransport([b"PONG\n"]))

    result = adapter.ping()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS


def test_real_drum_adapter_get_position_success() -> None:
    adapter = RealDrumAdapter(config=_drum_config(), transport=_FakeTransport([b"POSITION:4\n"]))

    result = adapter.get_position()

    assert isinstance(result, DrumPositionResult)
    assert result.ok is True
    assert result.position == 4


def test_real_drum_adapter_move_to_position_success() -> None:
    adapter = RealDrumAdapter(config=_drum_config(), transport=_FakeTransport([b"MOVED:7\n"]))

    result = adapter.move_to_position(7)

    assert result.ok is True
    assert result.position == 7


def test_real_drum_adapter_malformed_response_returns_safe_failure() -> None:
    adapter = RealDrumAdapter(config=_drum_config(), transport=_FakeTransport([123]))  # type: ignore[list-item]

    with pytest.raises(HardwareFailureError, match="malformed response"):
        adapter.get_position()


def test_real_drum_adapter_transport_timeout_and_error_handling_stays_safe() -> None:
    timeout_adapter = RealDrumAdapter(config=_drum_config(), transport=_RaisingTransport(TimeoutError("timed out")))
    error_adapter = RealDrumAdapter(config=_drum_config(), transport=_RaisingTransport(OSError("connect failed")))

    with pytest.raises(HardwareTimeoutError, match="timed out"):
        timeout_adapter.ping()
    with pytest.raises(HardwareUnavailableError, match="connect failed"):
        error_adapter.ping()


def test_real_provider_composition_still_works_with_operational_drum_transport() -> None:
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
        transport_overrides={"drum_controller": _FakeTransport([b"PONG\n", b"POSITION:2\n", b"MOVED:5\n"])},
    )

    ping_result = bundle.drum_controller.ping()
    position_result = bundle.drum_controller.get_position()
    move_result = bundle.drum_controller.move_to_position(5)

    assert bundle.provider is HardwareProvider.REAL
    assert ping_result.ok is True
    assert position_result.position == 2
    assert move_result.position == 5


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


def _drum_config():
    from app.hardware.transport_config import HardwareEndpointTransportConfig

    return HardwareEndpointTransportConfig.model_validate(
        _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM7")
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
