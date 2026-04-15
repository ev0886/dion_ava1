from __future__ import annotations

import pytest

from app.config import AppSettings, HardwareProvider
from app.hardware import (
    HardwareFailureError,
    HardwareOperationStatus,
    HardwareTimeoutError,
    RealRfidAdapter,
    create_hardware_bundle,
)


def test_real_rfid_adapter_ping_success_with_fake_transport() -> None:
    adapter = RealRfidAdapter(config=_rfid_config(), transport=_FakeTransport([b"PONG\n"]))

    result = adapter.ping()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS


def test_real_rfid_adapter_read_card_success_with_fake_transport() -> None:
    adapter = RealRfidAdapter(config=_rfid_config(), transport=_FakeTransport([b"UID:aa-bb cc\n"]))

    result = adapter.read_card()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert result.uid == "AABBCC"
    assert result.is_duplicate is False


def test_real_rfid_adapter_read_card_handles_no_card_response() -> None:
    adapter = RealRfidAdapter(config=_rfid_config(), transport=_FakeTransport([b"NO_CARD\n"]))

    result = adapter.read_card()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.NO_CARD
    assert result.uid is None
    assert result.is_duplicate is False


def test_real_rfid_adapter_malformed_response_raises_safe_failure() -> None:
    adapter = RealRfidAdapter(config=_rfid_config(), transport=_FakeTransport([123]))  # type: ignore[list-item]

    with pytest.raises(HardwareFailureError, match="malformed response"):
        adapter.read_card()


def test_real_rfid_adapter_clear_buffer_success() -> None:
    adapter = RealRfidAdapter(config=_rfid_config(), transport=_FakeTransport([b"CLEARED\n"]))

    result = adapter.clear_buffer()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS


def test_real_rfid_adapter_timeout_is_reported_as_safe_timeout() -> None:
    adapter = RealRfidAdapter(config=_rfid_config(), transport=_RaisingTransport(TimeoutError("timed out")))

    with pytest.raises(HardwareTimeoutError, match="timed out"):
        adapter.read_card()


def test_real_provider_composition_still_works_with_operational_rfid_transport() -> None:
    settings = AppSettings(
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _serial_endpoint_config(code="lock-1", driver_name="lock-driver", port="COM2"),
            "rfid_reader": _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM3"),
        },
    )

    bundle = create_hardware_bundle(
        settings,
        transport_overrides={"rfid_reader": _FakeTransport([b"PONG\n", b"UID:012345\n", b"CLEARED\n"])},
    )

    ping_result = bundle.rfid_reader.ping()
    read_result = bundle.rfid_reader.read_card()
    clear_result = bundle.rfid_reader.clear_buffer()

    assert bundle.provider is HardwareProvider.REAL
    assert ping_result.ok is True
    assert read_result.uid == "012345"
    assert clear_result.ok is True


def test_real_provider_composition_accepts_known_good_pi_rfid_shape_with_sdk_library() -> None:
    settings = AppSettings(
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _serial_endpoint_config(code="lock-1", driver_name="lock-driver", port="COM2"),
            "rfid_reader": _serial_endpoint_config(
                code="rfid-1",
                driver_name="rfid-driver",
                port="/dev/ttyACM0",
                sdk_library="/opt/dion_ava1/vendor/rusguard/linux_arm64_release/librgsec.so",
            ),
        },
    )

    bundle = create_hardware_bundle(
        settings,
        transport_overrides={"rfid_reader": _FakeTransport([b"PONG\n", b"UID:012345\n", b"CLEARED\n"])},
    )

    assert bundle.rfid_reader._config is not None
    assert bundle.rfid_reader._config.transport.sdk_library == "/opt/dion_ava1/vendor/rusguard/linux_arm64_release/librgsec.so"
    assert bundle.rfid_reader.ping().ok is True
    assert bundle.rfid_reader.read_card().uid == "012345"
    assert bundle.rfid_reader.clear_buffer().ok is True


class _FakeTransport:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.requests: list[tuple[bytes, int | None]] = []

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        self.requests.append((payload, timeout_ms))
        if not self._responses:
            raise AssertionError("No fake transport responses remain.")
        response = self._responses.pop(0)
        return response  # type: ignore[return-value]


class _RaisingTransport:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        raise self._error


def _rfid_config():
    from app.hardware.transport_config import HardwareEndpointTransportConfig

    return HardwareEndpointTransportConfig.model_validate(_serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM7"))


def _serial_endpoint_config(
    *,
    code: str,
    driver_name: str,
    port: str,
    sdk_library: str | None = None,
) -> dict[str, object]:
    transport: dict[str, object] = {
        "transport": "serial",
        "port": port,
        "baudrate": 9600,
        "data_bits": 8,
        "parity": "none",
        "stop_bits": 1,
    }
    if sdk_library is not None:
        transport["sdk_library"] = sdk_library
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
        "transport": transport,
    }
