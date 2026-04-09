from __future__ import annotations

from pathlib import Path

import pytest

from app.application.composition import create_bootstrapped_application_container
from app.config import AppSettings, HardwareProvider
from app.domain.enums import StartupReadinessStatus
from app.hardware import (
    HardwareTimeoutError,
    RealRfidAdapter,
    RusGuardSdkAcmTransport,
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
    assert isinstance(bundle.rfid_reader._transport, RusGuardSdkAcmTransport)


def test_rusguard_sdk_acm_transport_uses_exact_ttyacm0_and_status_no_mask() -> None:
    sdk_instances: list[_FakeRusGuardSdk] = []

    def sdk_factory(library_path: Path) -> _FakeRusGuardSdk:
        sdk = _FakeRusGuardSdk(
            library_path=library_path,
            endpoints=(
                _endpoint_info(index=0, address="/dev/ttyUSB0"),
                _endpoint_info(index=1, address="/dev/ttyACM0"),
            ),
        )
        sdk_instances.append(sdk)
        return sdk

    transport = RusGuardSdkAcmTransport(
        sdk_factory=sdk_factory,
        library_path=Path("/opt/dion_ava1/vendor/rusguard/sdk/librgsec.so"),
    )

    response = transport.request(b"PING\n")

    assert response == b"PONG\n"
    assert sdk_instances[0].calls == [
        ("initialize",),
        ("find_endpoint_infos", 2),
        ("diagnose_acm_status_no_mask_endpoint", "/dev/ttyACM0"),
        ("uninitialize",),
    ]


def test_rusguard_sdk_acm_transport_fails_clearly_when_ttyacm0_is_missing() -> None:
    transport = RusGuardSdkAcmTransport(
        sdk_factory=lambda library_path: _FakeRusGuardSdk(
            library_path=library_path,
            endpoints=(_endpoint_info(index=0, address="/dev/ttyUSB0"),),
        ),
        library_path=Path("/opt/dion_ava1/vendor/rusguard/sdk/librgsec.so"),
    )

    with pytest.raises(OSError, match="/dev/ttyACM0"):
        transport.request(b"PING\n")


def test_rusguard_sdk_acm_transport_rejects_unproven_operations() -> None:
    transport = RusGuardSdkAcmTransport(
        sdk_factory=lambda library_path: _FakeRusGuardSdk(
            library_path=library_path,
            endpoints=(_endpoint_info(index=0, address="/dev/ttyACM0"),),
        )
    )

    with pytest.raises(NotImplementedError, match="supports ping only"):
        transport.request(b"READ\n")


def test_real_readiness_can_become_healthy_when_rfid_lock_and_drum_transports_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.hardware import factory as hardware_factory

    def fake_create_transport_client(config):
        if config is None:
            return None
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


class _FakeRusGuardSdk:
    def __init__(
        self,
        *,
        library_path: Path,
        endpoints,
        open_code: int = 0,
        status_code: int = 0,
        close_code: int = 0,
    ) -> None:
        self.library_path = library_path
        self._endpoints = tuple(endpoints)
        self._open_code = open_code
        self._status_code = status_code
        self._close_code = close_code
        self.calls: list[tuple[object, ...]] = []

    def initialize(self) -> None:
        self.calls.append(("initialize",))

    def find_endpoint_infos(self, endpoint_type_mask: int):
        self.calls.append(("find_endpoint_infos", endpoint_type_mask))
        return self._endpoints

    def diagnose_acm_status_no_mask_endpoint(self, endpoint_info):
        from app.diagnostics.rusguard_sdk import AcmStatusNoMaskDiagnosticResult, OperationResult

        self.calls.append(("diagnose_acm_status_no_mask_endpoint", endpoint_info.address))
        return AcmStatusNoMaskDiagnosticResult(
            endpoint_info=endpoint_info,
            open_result=_operation_result(self._open_code),
            status_result=_operation_result(self._status_code) if self._open_code == 0 else None,
            close_result=_operation_result(self._close_code) if self._open_code == 0 else None,
        )

    def uninitialize(self) -> None:
        self.calls.append(("uninitialize",))


def _rfid_config():
    from app.hardware.transport_config import HardwareEndpointTransportConfig

    return HardwareEndpointTransportConfig.model_validate(
        _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM7")
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


def _endpoint_info(*, index: int, address: str):
    from app.diagnostics.rusguard_sdk import EndpointInfo

    return EndpointInfo(index=index, type=2, address=address, friendly_name="RusGuard Reader")


def _operation_result(code: int):
    from app.diagnostics.rusguard_sdk import OperationResult, decode_api_error

    code_name, code_message = decode_api_error(code)
    return OperationResult(ok=code == 0, code=code, code_name=code_name, code_message=code_message)
