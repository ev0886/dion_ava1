from __future__ import annotations

from pathlib import Path

import pytest

from app.application.composition import create_bootstrapped_application_container
from app.config import AppSettings, HardwareProvider
from app.domain.enums import StartupReadinessStatus
from app.hardware import (
    HardwareTimeoutError,
    RealRfidAdapter,
    RusGuardAcmStatusTransport,
    SerialTransport,
    TcpTransport,
    create_hardware_bundle,
)
from app.hardware.transport_config import EndpointTimeoutSettings, SerialTransportSettings, TcpTransportSettings


def test_serial_transport_request_response_happy_path() -> None:
    transport = SerialTransport(
        settings=SerialTransportSettings(
            transport="serial",
            port="COM7",
            baudrate=9600,
            data_bits=8,
            parity="none",
            stop_bits=1,
        ),
        timeouts=EndpointTimeoutSettings(connect_timeout_ms=1000, read_timeout_ms=1000, write_timeout_ms=1000),
        serial_module_loader=lambda: _FakeSerialModule([b"PONG\n"]),
    )

    response = transport.request(b"PING\n")

    assert response == b"PONG\n"


def test_serial_transport_request_sequence_flushes_each_write_before_reading() -> None:
    serial_module = _FakeSerialModule([bytes.fromhex("21 AA AA C4"), bytes.fromhex("25 C0")], require_flush=True)
    transport = SerialTransport(
        settings=SerialTransportSettings(
            transport="serial",
            port="COM7",
            baudrate=9600,
            data_bits=8,
            parity="none",
            stop_bits=1,
        ),
        timeouts=EndpointTimeoutSettings(connect_timeout_ms=1000, read_timeout_ms=1000, write_timeout_ms=1000),
        serial_module_loader=lambda: serial_module,
    )

    responses = transport.request_sequence([bytes.fromhex("11 00 01 F5"), bytes.fromhex("30 D5")])

    assert responses == [bytes.fromhex("21 AA AA C4"), bytes.fromhex("25 C0")]
    assert serial_module.last_connection is not None
    assert serial_module.last_connection.writes == [bytes.fromhex("11 00 01 F5"), bytes.fromhex("30 D5")]
    assert serial_module.last_connection.flush_count == 2
    assert serial_module.last_connection.events[:3] == ["write", "flush", "read"]
    assert serial_module.last_connection.events.count("write") == 2
    assert serial_module.last_connection.events.count("flush") == 2


def test_tcp_transport_request_response_happy_path() -> None:
    fake_socket = _FakeSocket(response=b"UID:ABC123\n")
    transport = TcpTransport(
        settings=TcpTransportSettings(transport="tcp", host="127.0.0.1", port=9001),
        timeouts=EndpointTimeoutSettings(connect_timeout_ms=1000, read_timeout_ms=1000, write_timeout_ms=1000),
        socket_factory=lambda address, timeout: fake_socket,
    )

    response = transport.request(b"READ\n")

    assert response == b"UID:ABC123\n"
    assert fake_socket.sent_payloads == [b"READ\n"]


def test_transport_timeout_error_is_mapped_to_safe_adapter_timeout() -> None:
    adapter = RealRfidAdapter(
        config=_rfid_config(),
        transport=_TimeoutStatusTransport(),
    )

    with pytest.raises(HardwareTimeoutError, match="read timed out"):
        adapter.ping()


def test_real_provider_composition_uses_actual_transport_implementations_by_default() -> None:
    settings = AppSettings(
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _lock_serial_endpoint_config(code="lock-1", driver_name="lock-driver", port="COM2"),
            "rfid_reader": _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM3"),
        },
    )

    bundle = create_hardware_bundle(settings)

    assert isinstance(bundle.drum_controller._transport, SerialTransport)
    assert isinstance(bundle.lock_controller._transport, SerialTransport)
    assert isinstance(bundle.rfid_reader._transport, RusGuardAcmStatusTransport)


def test_real_readiness_can_become_healthy_when_rfid_lock_and_drum_transports_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.hardware import factory as hardware_factory

    def fake_create_transport_client(config):
        if config is None:
            return None
        if config.endpoint.code == "lock-1":
            return _FakeTransport([bytes.fromhex("02 00 00 8F 10 02 03 BA 13 01")])
        return _FakeTransport([bytes.fromhex("24 00 00 C1")])

    def fake_create_rfid_transport_client(config):
        if config is None:
            return None
        return _FakeStatusTransport()

    monkeypatch.setattr(hardware_factory, "_create_transport_client", fake_create_transport_client)
    monkeypatch.setattr(hardware_factory, "_create_rfid_transport_client", fake_create_rfid_transport_client)

    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="real_partial_ready.sqlite3",
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _lock_serial_endpoint_config(code="lock-1", driver_name="lock-driver", port="COM2"),
            "rfid_reader": _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM3"),
        },
    )

    container = create_bootstrapped_application_container(settings)
    try:
        result = container.services.startup.run_startup_checks()

        assert result.readiness_status is StartupReadinessStatus.READY
        entries = {entry.device_type: entry for entry in result.hardware.entries}
        assert entries["rfid_reader"].is_available is True
        assert entries["lock_controller"].is_available is True
        assert entries["drum_controller"].is_available is True
    finally:
        container.close()


class _FakeTransport:
    def __init__(self, responses: list[bytes]) -> None:
        self._responses = list(responses)

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        if not self._responses:
            raise AssertionError("No fake responses remain.")
        return self._responses.pop(0)

    def send(self, payload: bytes) -> None:
        return None


class _FakeStatusTransport:
    def ping(self, *, timeout_ms: int | None = None) -> None:
        return None


class _TimeoutStatusTransport:
    def ping(self, *, timeout_ms: int | None = None) -> None:
        raise TimeoutError("read timed out")


class _FakeSerialModule:
    def __init__(self, responses: list[bytes], *, require_flush: bool = False) -> None:
        self._responses = responses
        self._require_flush = require_flush
        self.last_connection: _FakeSerialConnection | None = None

    def Serial(self, **kwargs):  # noqa: N802
        self.last_connection = _FakeSerialConnection(self._responses, require_flush=self._require_flush)
        return self.last_connection


class _FakeSerialConnection:
    def __init__(self, responses: list[bytes], *, require_flush: bool = False) -> None:
        self._responses = responses
        self._require_flush = require_flush
        self.writes: list[bytes] = []
        self.events: list[str] = []
        self.flush_count = 0
        self._current = b""
        self.in_waiting = 0
        self._flushed_since_write = not require_flush
        self._response_ready = False

    def reset_input_buffer(self) -> None:
        return None

    def reset_output_buffer(self) -> None:
        return None

    def write(self, payload: bytes) -> None:
        self.writes.append(payload)
        self.events.append("write")
        if self._require_flush:
            self._flushed_since_write = False
            self._response_ready = False
        else:
            self._response_ready = True

    def flush(self) -> None:
        self.flush_count += 1
        self.events.append("flush")
        self._flushed_since_write = True
        self._response_ready = True

    def read(self, size: int = 1) -> bytes:
        self.events.append("read")
        if self._require_flush and not self._flushed_since_write:
            self.in_waiting = 0
            return b""
        if not self._current and self._response_ready and self._responses:
            self._current = self._responses.pop(0)
            self.in_waiting = len(self._current)
            self._response_ready = False
        if not self._current:
            self.in_waiting = 0
            return b""
        chunk = self._current[:size]
        self._current = self._current[size:]
        self.in_waiting = len(self._current)
        return chunk

    def read_until(self, separator: bytes = b"\n") -> bytes:
        if not self._responses:
            return b""
        return self._responses.pop(0)

    def close(self) -> None:
        return None


class _FakeSocket:
    def __init__(self, *, response: bytes) -> None:
        self._response = response
        self.sent_payloads: list[bytes] = []
        self._sent = False

    def settimeout(self, timeout: float) -> None:
        return None

    def sendall(self, payload: bytes) -> None:
        self.sent_payloads.append(payload)

    def recv(self, size: int) -> bytes:
        if self._sent:
            return b""
        self._sent = True
        return self._response

    def close(self) -> None:
        return None


def _rfid_config():
    from app.hardware.transport_config import RfidHardwareEndpointTransportConfig

    return RfidHardwareEndpointTransportConfig.model_validate(
        _minimal_rfid_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="/dev/ttyACM0")
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


def _minimal_rfid_endpoint_config(*, code: str, driver_name: str, port: str) -> dict[str, object]:
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
