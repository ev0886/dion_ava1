from __future__ import annotations

import struct

import pytest

from app.config import AppSettings, HardwareProvider
from app.hardware import (
    HardwareFailureError,
    HardwareOperationStatus,
    HardwareTimeoutError,
    HardwareUnavailableError,
    LinuxInputEventTransport,
    RealRfidAdapter,
    create_hardware_bundle,
)
from app.hardware.transport_config import (
    EndpointTimeoutSettings,
    LinuxInputTransportSettings,
    RfidHardwareEndpointTransportConfig,
)


def test_real_rfid_adapter_ping_success_with_fake_transport() -> None:
    adapter = RealRfidAdapter(config=_linux_input_rfid_config(), transport=_FakeTransport([b"PONG\n"]))

    result = adapter.ping()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS


def test_real_rfid_adapter_ping_success_with_rusguard_acm_echo_response() -> None:
    transport = _FakeTransport([b"PING\n"])
    adapter = RealRfidAdapter(config=_serial_rusguard_acm_config(), transport=transport)

    result = adapter.ping()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert transport.requests == [b"PING\n"]


def test_real_rfid_adapter_reads_uid_from_linux_input_events() -> None:
    adapter = RealRfidAdapter(
        config=_linux_input_rfid_config(),
        transport=_linux_input_transport(
            [
                _event_chunk(1, 18, 1),
                _event_chunk(0, 0, 0),
                _event_chunk(1, 3, 1),
                _event_chunk(1, 8, 1),
                _event_chunk(1, 7, 1),
                _event_chunk(1, 8, 1),
                _event_chunk(1, 46, 1),
                _event_chunk(1, 11, 1),
                _event_chunk(1, 11, 1),
                _event_chunk(1, 5, 1),
                _event_chunk(1, 6, 1),
                _event_chunk(1, 28, 1),
            ]
        ),
    )

    result = adapter.read_card()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert result.uid == "E2767C0045"
    assert result.is_duplicate is False


def test_real_rfid_adapter_reads_one_card_from_rusguard_acm_serial_transport() -> None:
    transport = _FakeTransport([b"E2 76-7C 00 45\n"])
    adapter = RealRfidAdapter(config=_serial_rusguard_acm_config(), transport=transport)

    result = adapter.read_card()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert result.uid == "E2767C0045"
    assert result.is_duplicate is False
    assert transport.requests == [b""]


def test_real_rfid_adapter_reads_binary_uid_from_rusguard_acm_serial_transport() -> None:
    transport = _FakeTransport([b"\xe2v|\x00E"])
    adapter = RealRfidAdapter(config=_serial_rusguard_acm_config(), transport=transport)

    result = adapter.read_card()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert result.uid == "E2767C0045"
    assert result.is_duplicate is False
    assert transport.requests == [b""]


def test_real_rfid_adapter_marks_duplicate_binary_rusguard_acm_reads() -> None:
    adapter = RealRfidAdapter(config=_serial_rusguard_acm_config(), transport=_FakeTransport([b"\xe2v|\x00E", b"\xe2v|\x00E"]))

    first_result = adapter.read_card()
    second_result = adapter.read_card()

    assert first_result.uid == "E2767C0045"
    assert first_result.is_duplicate is False
    assert second_result.uid == "E2767C0045"
    assert second_result.is_duplicate is True


def test_real_rfid_adapter_reads_real_like_linux_input_sequence_with_separators_and_key_releases() -> None:
    adapter = RealRfidAdapter(
        config=_linux_input_rfid_config(),
        transport=_linux_input_transport(
            [
                _event_chunk(1, 42, 1),
                _event_chunk(1, 32, 1),
                _event_chunk(1, 32, 0),
                _event_chunk(0, 0, 0),
                _event_chunk(1, 18, 1),
                _event_chunk(1, 18, 0),
                _event_chunk(1, 50, 1),
                _event_chunk(1, 50, 0),
                _event_chunk(1, 24, 1),
                _event_chunk(1, 24, 0),
                _event_chunk(1, 12, 1),
                _event_chunk(1, 12, 0),
                _event_chunk(1, 22, 1),
                _event_chunk(1, 22, 0),
                _event_chunk(1, 31, 1),
                _event_chunk(1, 31, 0),
                _event_chunk(1, 18, 1),
                _event_chunk(1, 18, 0),
                _event_chunk(1, 19, 1),
                _event_chunk(1, 19, 0),
                _event_chunk(1, 12, 1),
                _event_chunk(1, 12, 0),
                _event_chunk(1, 2, 1),
                _event_chunk(1, 2, 0),
                _event_chunk(1, 96, 1),
            ]
        ),
    )

    result = adapter.read_card()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert result.uid == "DEMOUSER1"
    assert result.is_duplicate is False


def test_real_rfid_adapter_no_card_when_linux_input_reader_stays_idle() -> None:
    adapter = RealRfidAdapter(
        config=_linux_input_rfid_config(),
        transport=_linux_input_transport([], readable_sequence=[False]),
    )

    result = adapter.read_card()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.NO_CARD
    assert result.uid is None
    assert result.is_duplicate is False


def test_real_rfid_adapter_timeout_is_reported_for_incomplete_linux_input_scan() -> None:
    adapter = RealRfidAdapter(
        config=_linux_input_rfid_config(),
        transport=_linux_input_transport([_event_chunk(1, 18, 1), _event_chunk(1, 3, 1)], readable_sequence=[True, True, False]),
    )

    with pytest.raises(HardwareTimeoutError, match="end-of-card marker"):
        adapter.read_card()


def test_real_rfid_adapter_reports_timeout_when_rusguard_acm_scan_does_not_arrive() -> None:
    adapter = RealRfidAdapter(config=_serial_rusguard_acm_config(), transport=_FakeTransport([TimeoutError("scan timed out")]))

    with pytest.raises(HardwareTimeoutError, match="scan timed out"):
        adapter.read_card()


def test_real_rfid_adapter_unavailable_when_linux_input_device_cannot_be_opened() -> None:
    transport = LinuxInputEventTransport(
        settings=LinuxInputTransportSettings(transport="linux_input", device_path="/dev/input/event7"),
        timeouts=EndpointTimeoutSettings(connect_timeout_ms=1000, read_timeout_ms=1000, write_timeout_ms=1000),
        device_opener=lambda device_path, nonblocking: (_ for _ in ()).throw(OSError("Permission denied")),
    )
    adapter = RealRfidAdapter(config=_linux_input_rfid_config(), transport=transport)

    with pytest.raises(HardwareUnavailableError, match="Permission denied"):
        adapter.read_card()


def test_real_rfid_adapter_malformed_linux_input_sequence_raises_safe_failure() -> None:
    adapter = RealRfidAdapter(
        config=_linux_input_rfid_config(),
        transport=_linux_input_transport([_event_chunk(1, 59, 1)]),
    )

    with pytest.raises(HardwareFailureError, match="unsupported read response"):
        adapter.read_card()


def test_real_rfid_adapter_rejects_unsupported_rusguard_acm_read_response() -> None:
    adapter = RealRfidAdapter(config=_serial_rusguard_acm_config(), transport=_FakeTransport([b"PING\n"]))

    with pytest.raises(HardwareFailureError, match="unsupported read response: 'PING'"):
        adapter.read_card()


def test_real_rfid_adapter_rejects_empty_binary_rusguard_acm_read_response() -> None:
    adapter = RealRfidAdapter(config=_serial_rusguard_acm_config(), transport=_FakeTransport([b""]))

    with pytest.raises(HardwareFailureError, match="empty card UID"):
        adapter.read_card()


def test_real_rfid_adapter_reads_uid_from_generic_serial_text_transport() -> None:
    transport = _FakeTransport([b"UID:E2 76-7C 00 45\n"])
    adapter = RealRfidAdapter(config=_generic_serial_rfid_config(), transport=transport)

    result = adapter.read_card()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert result.uid == "E2767C0045"
    assert result.is_duplicate is False
    assert transport.requests == [b"READ\n"]


def test_real_rfid_adapter_clear_buffer_success_with_linux_input_transport() -> None:
    device = _FakeInputDevice([_event_chunk(1, 18, 1), _event_chunk(1, 28, 1)])
    transport = LinuxInputEventTransport(
        settings=LinuxInputTransportSettings(transport="linux_input", device_path="/dev/input/event7"),
        timeouts=EndpointTimeoutSettings(connect_timeout_ms=1000, read_timeout_ms=1000, write_timeout_ms=1000),
        device_opener=lambda device_path, nonblocking: device,
    )
    adapter = RealRfidAdapter(config=_linux_input_rfid_config(), transport=transport)

    result = adapter.clear_buffer()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert device.read_calls == 2


def test_real_provider_composition_supports_linux_input_rfid_transport() -> None:
    settings = AppSettings(
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _lock_serial_endpoint_config(code="lock-1", driver_name="lock-driver", port="COM2"),
            "rfid_reader": _linux_input_endpoint_config(code="rfid-1", driver_name="rusguard-hid", device_path="/dev/input/event7"),
        },
    )

    bundle = create_hardware_bundle(
        settings,
        transport_overrides={"rfid_reader": _FakeTransport([b"PONG\n", b"UID:E2767C0045\n", b"CLEARED\n"])},
    )

    ping_result = bundle.rfid_reader.ping()
    read_result = bundle.rfid_reader.read_card()
    clear_result = bundle.rfid_reader.clear_buffer()

    assert bundle.provider is HardwareProvider.REAL
    assert ping_result.ok is True
    assert read_result.uid == "E2767C0045"
    assert clear_result.ok is True


def test_real_provider_composition_supports_rusguard_acm_rfid_transport() -> None:
    settings = AppSettings(
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _lock_serial_endpoint_config(code="lock-1", driver_name="lock-driver", port="COM2"),
            "rfid_reader": _serial_endpoint_config(
                code="rfid-1",
                driver_name="rusguard-acm",
                port="/dev/serial/by-id/usb-RusGuard_Reader_0F00C022-if01",
            ),
        },
    )

    transport = _FakeTransport([b"PING\n", b"E2767C0045\n"])
    bundle = create_hardware_bundle(settings, transport_overrides={"rfid_reader": transport})

    ping_result = bundle.rfid_reader.ping()
    read_result = bundle.rfid_reader.read_card()

    assert bundle.provider is HardwareProvider.REAL
    assert ping_result.ok is True
    assert read_result.uid == "E2767C0045"
    assert transport.requests == [b"PING\n", b""]


class _FakeTransport:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.requests: list[bytes] = []

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        self.requests.append(payload)
        if not self._responses:
            raise AssertionError("No fake transport responses remain.")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response  # type: ignore[return-value]


class _FakeInputDevice:
    def __init__(self, chunks: list[bytes], *, readable_sequence: list[bool] | None = None) -> None:
        self._chunks = list(chunks)
        self._readable_sequence = list(readable_sequence) if readable_sequence is not None else None
        self.read_calls = 0
        self.closed = False

    def read(self) -> bytes:
        self.read_calls += 1
        if not self._chunks:
            return b""
        return self._chunks.pop(0)

    def wait_until_readable(self, timeout_seconds: float) -> bool:
        if self._readable_sequence is not None:
            if not self._readable_sequence:
                return False
            return self._readable_sequence.pop(0)
        return bool(self._chunks)

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "_FakeInputDevice":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _linux_input_transport(
    chunks: list[bytes],
    *,
    readable_sequence: list[bool] | None = None,
) -> LinuxInputEventTransport:
    return LinuxInputEventTransport(
        settings=LinuxInputTransportSettings(transport="linux_input", device_path="/dev/input/event7"),
        timeouts=EndpointTimeoutSettings(connect_timeout_ms=1000, read_timeout_ms=1000, write_timeout_ms=1000),
        device_opener=lambda device_path, nonblocking: _FakeInputDevice(chunks, readable_sequence=readable_sequence),
    )


def _linux_input_rfid_config() -> RfidHardwareEndpointTransportConfig:
    return RfidHardwareEndpointTransportConfig.model_validate(
        _linux_input_endpoint_config(code="rfid-1", driver_name="rusguard-hid", device_path="/dev/input/event7")
    )


def _serial_rusguard_acm_config() -> RfidHardwareEndpointTransportConfig:
    return RfidHardwareEndpointTransportConfig.model_validate(
        _serial_endpoint_config(code="rfid-1", driver_name="rusguard-acm", port="/dev/ttyACM0")
    )


def _generic_serial_rfid_config() -> RfidHardwareEndpointTransportConfig:
    return RfidHardwareEndpointTransportConfig.model_validate(
        _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM7")
    )


def _linux_input_endpoint_config(*, code: str, driver_name: str, device_path: str) -> dict[str, object]:
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
            "transport": "linux_input",
            "device_path": device_path,
        },
    }


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


def _event_chunk(event_type: int, code: int, value: int) -> bytes:
    return struct.pack("<qqHHi", 0, 0, event_type, code, value)
