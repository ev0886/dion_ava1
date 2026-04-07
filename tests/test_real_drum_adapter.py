from __future__ import annotations

import pytest

from app.config import AppSettings, HardwareProvider
from app.hardware import (
    DrumPositionResult,
    HardwareBusyError,
    HardwareFailureError,
    HardwareOperationStatus,
    HardwareTimeoutError,
    HardwareUnavailableError,
    RealDrumAdapter,
    create_hardware_bundle,
)


def test_real_drum_adapter_ping_success_with_fake_transport() -> None:
    adapter = RealDrumAdapter(config=_drum_config(), transport=_FakeTransport([bytes.fromhex("24 00 04 C5")]))

    result = adapter.ping()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS


def test_real_drum_adapter_get_position_success() -> None:
    transport = _FakeTransport([bytes.fromhex("24 00 04 C5")])
    adapter = RealDrumAdapter(config=_drum_config(), transport=transport)

    result = adapter.get_position()

    assert isinstance(result, DrumPositionResult)
    assert result.ok is True
    assert result.position == 4
    assert transport.request_payloads == [bytes.fromhex("12 00 00 F7")]
    assert transport.sent_payloads == [bytes.fromhex("30 D5")]


def test_real_drum_adapter_move_to_position_success() -> None:
    transport = _FakeTransport([], sequence_responses=[bytes.fromhex("21 AA AA C4"), bytes.fromhex("25 C0")])
    adapter = RealDrumAdapter(config=_drum_config(), transport=transport)

    result = adapter.move_to_position(7)

    assert result.ok is True
    assert result.position == 7
    assert transport.sequence_payloads == [[bytes.fromhex("11 00 07 F3"), bytes.fromhex("30 D5")]]
    assert transport.request_payloads == []


def test_real_drum_adapter_move_to_position_busy_maps_to_busy_error() -> None:
    adapter = RealDrumAdapter(
        config=_drum_config(),
        transport=_FakeTransport([], sequence_responses=[bytes.fromhex("22 AA AA C7"), bytes.fromhex("25 C0")]),
    )

    with pytest.raises(HardwareBusyError, match="busy"):
        adapter.move_to_position(7)


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
            "lock_controller": _lock_serial_endpoint_config(code="lock-1", driver_name="lock-driver", port="COM2"),
            "rfid_reader": _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM3"),
        },
    )

    bundle = create_hardware_bundle(
        settings,
        transport_overrides={
            "drum_controller": _FakeTransport(
                [bytes.fromhex("24 00 02 C3"), bytes.fromhex("24 00 02 C3")],
                sequence_responses=[bytes.fromhex("21 AA AA C4"), bytes.fromhex("25 C0")],
            )
        },
    )

    ping_result = bundle.drum_controller.ping()
    position_result = bundle.drum_controller.get_position()
    move_result = bundle.drum_controller.move_to_position(5)

    assert bundle.provider is HardwareProvider.REAL
    assert ping_result.ok is True
    assert position_result.position == 2
    assert move_result.position == 5


class _FakeTransport:
    def __init__(self, responses: list[object], *, sequence_responses: list[object] | None = None) -> None:
        self._responses = list(responses)
        self._sequence_responses = list(sequence_responses or [])
        self.request_payloads: list[bytes] = []
        self.sent_payloads: list[bytes] = []
        self.sequence_payloads: list[list[bytes]] = []

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        self.request_payloads.append(payload)
        if not self._responses:
            raise AssertionError("No fake responses remain.")
        response = self._responses.pop(0)
        return response  # type: ignore[return-value]

    def send(self, payload: bytes) -> None:
        self.sent_payloads.append(payload)

    def request_sequence(self, payloads: list[bytes], *, timeout_ms: int | None = None) -> list[bytes]:
        self.sequence_payloads.append(list(payloads))
        if len(self._sequence_responses) < len(payloads):
            raise AssertionError("Not enough fake sequence responses remain.")
        responses = self._sequence_responses[: len(payloads)]
        del self._sequence_responses[: len(payloads)]
        return responses  # type: ignore[return-value]


class _RaisingTransport:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        raise self._error

    def send(self, payload: bytes) -> None:
        raise self._error

    def request_sequence(self, payloads: list[bytes], *, timeout_ms: int | None = None) -> list[bytes]:
        raise self._error


def _drum_config():
    from app.hardware.transport_config import DrumHardwareEndpointTransportConfig

    return DrumHardwareEndpointTransportConfig.model_validate(
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
