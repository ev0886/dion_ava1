from __future__ import annotations

from pathlib import Path

import pytest

from app.application.composition import create_bootstrapped_application_container
from app.config import AppSettings, HardwareProvider
from app.domain.enums import StartupReadinessStatus
from app.hardware import (
    HardwareTimeoutError,
    RealRfidAdapter,
    RealHardwareSettings,
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
        transport=SerialTransport(
            settings=SerialTransportSettings(
                transport="serial",
                port="COM7",
                baudrate=9600,
                data_bits=8,
                parity="none",
                stop_bits=1,
            ),
            timeouts=EndpointTimeoutSettings(connect_timeout_ms=1000, read_timeout_ms=1000, write_timeout_ms=1000),
            serial_module_loader=lambda: _FakeSerialModule([b""]),
        ),
    )

    with pytest.raises(HardwareTimeoutError, match="read timed out"):
        adapter.ping()


def test_real_provider_composition_uses_actual_transport_implementations_by_default() -> None:
    settings = AppSettings(
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _tcp_endpoint_config(code="lock-1", driver_name="lock-driver", host="127.0.0.1", port=9001),
            "rfid_reader": _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM3"),
        },
    )

    bundle = create_hardware_bundle(settings)

    assert isinstance(bundle.drum_controller._transport, SerialTransport)
    assert isinstance(bundle.lock_controller._transport, TcpTransport)
    assert isinstance(bundle.rfid_reader._transport, SerialTransport)


def test_exact_known_good_pi_runtime_config_shape_is_accepted() -> None:
    config = RealHardwareSettings.model_validate(_known_good_pi_real_runtime_config())

    assert config.drum_controller is not None
    assert config.drum_controller.protocol.move_completion_timeout_ms == 35000
    assert config.drum_controller.protocol.post_move_unlock_delay_ms == 1500
    assert config.lock_controller is not None
    assert config.lock_controller.protocol.board_address == 0
    assert config.rfid_reader is not None
    assert config.rfid_reader.transport.port == "/dev/ttyACM0"
    assert config.rfid_reader.transport.sdk_library == "/opt/dion_ava1/vendor/rusguard/linux_arm64_release/librgsec.so"


def test_real_provider_bundle_accepts_exact_known_good_pi_runtime_config_shape() -> None:
    settings = AppSettings(
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints=_known_good_pi_real_runtime_config(),
    )

    bundle = create_hardware_bundle(settings)

    assert isinstance(bundle.drum_controller._transport, SerialTransport)
    assert isinstance(bundle.lock_controller._transport, SerialTransport)
    assert isinstance(bundle.rfid_reader._transport, RusGuardAcmStatusTransport)
    assert bundle.rfid_reader._config is not None
    assert bundle.rfid_reader._config.transport.sdk_library == "/opt/dion_ava1/vendor/rusguard/linux_arm64_release/librgsec.so"


def test_real_readiness_can_become_healthy_when_rfid_lock_and_drum_transports_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.hardware import factory as hardware_factory

    def fake_create_transport_client(config):
        if config is None:
            return None
        if config.endpoint.code == "rfid-1":
            return _FakeTransport([b"PONG\n"])
        if config.endpoint.code == "lock-1":
            return _FakeTransport([b"PONG\n"])
        return _FakeTransport([b"PONG\n"])

    monkeypatch.setattr(hardware_factory, "_create_transport_client", fake_create_transport_client)
    monkeypatch.setattr(hardware_factory, "_create_rfid_transport_client", fake_create_transport_client)

    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename="real_partial_ready.sqlite3",
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _tcp_endpoint_config(code="lock-1", driver_name="lock-driver", host="127.0.0.1", port=9001),
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


class _FakeSerialModule:
    def __init__(self, responses: list[bytes]) -> None:
        self._responses = responses

    def Serial(self, **kwargs):  # noqa: N802
        return _FakeSerialConnection(self._responses)


class _FakeSerialConnection:
    def __init__(self, responses: list[bytes]) -> None:
        self._responses = responses
        self.writes: list[bytes] = []

    def reset_input_buffer(self) -> None:
        return None

    def reset_output_buffer(self) -> None:
        return None

    def write(self, payload: bytes) -> None:
        self.writes.append(payload)

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
    from app.hardware.transport_config import HardwareEndpointTransportConfig

    return HardwareEndpointTransportConfig.model_validate(
        _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM7")
    )


def _serial_endpoint_config(*, code: str, driver_name: str, port: str, sdk_library: str | None = None) -> dict[str, object]:
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


def _known_good_pi_real_runtime_config() -> dict[str, object]:
    return {
        "drum_controller": {
            "endpoint": {
                "code": "drum-1",
                "driver_name": "drum-driver",
                "enabled": True,
                "timeouts": {
                    "connect_timeout_ms": 1000,
                    "read_timeout_ms": 1000,
                    "write_timeout_ms": 1000,
                },
            },
            "protocol": {
                "move_completion_timeout_ms": 35000,
                "post_move_unlock_delay_ms": 1500,
            },
            "transport": {
                "transport": "serial",
                "port": "/dev/serial/by-path/platform-1000110000.pcie-pci-0001:01:00.0-usb-0:1.2:1.0-port0",
                "baudrate": 9600,
                "data_bits": 8,
                "parity": "none",
                "stop_bits": 1,
            },
        },
        "lock_controller": {
            "endpoint": {
                "code": "lock-1",
                "driver_name": "lock-driver",
                "enabled": True,
                "timeouts": {
                    "connect_timeout_ms": 1000,
                    "read_timeout_ms": 1000,
                    "write_timeout_ms": 1000,
                },
            },
            "protocol": {
                "board_address": 0,
            },
            "transport": {
                "transport": "serial",
                "port": "/dev/serial/by-path/platform-1000110000.pcie-pci-0001:01:00.0-usb-0:1.1:1.0-port0",
                "baudrate": 19200,
                "data_bits": 8,
                "parity": "none",
                "stop_bits": 1,
            },
        },
        "rfid_reader": {
            "endpoint": {
                "code": "rfid-1",
                "driver_name": "rfid-driver",
                "enabled": True,
                "timeouts": {
                    "connect_timeout_ms": 1000,
                    "read_timeout_ms": 1000,
                    "write_timeout_ms": 1000,
                },
            },
            "transport": {
                "transport": "serial",
                "port": "/dev/ttyACM0",
                "sdk_library": "/opt/dion_ava1/vendor/rusguard/linux_arm64_release/librgsec.so",
                "baudrate": 9600,
                "data_bits": 8,
                "parity": "none",
                "stop_bits": 1,
            },
        },
    }
