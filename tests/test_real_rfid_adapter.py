from __future__ import annotations

import ctypes

import pytest

from app.config import AppSettings, HardwareProvider
from app.hardware import (
    HardwareOperationStatus,
    HardwareProtocolNotImplementedError,
    HardwareTimeoutError,
    RealRfidAdapter,
    RusGuardAcmStatusTransport,
    create_hardware_bundle,
)
from app.hardware.rfid_rusguard import _RgCardInfo, _RgEndpointInfo


def test_real_rfid_adapter_ping_success_with_fake_status_transport() -> None:
    adapter = RealRfidAdapter(config=_rfid_config(), transport=_FakeStatusTransport())

    result = adapter.ping()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert adapter._transport.ping_calls == [1000]


def test_real_rfid_adapter_read_card_returns_normalized_uid_and_tracks_duplicates() -> None:
    adapter = RealRfidAdapter(
        config=_rfid_config(),
        transport=_FakeStatusTransport(read_results=[bytes.fromhex("01 23 45 67 89 AB CD"), bytes.fromhex("01 23 45 67 89 AB CD")]),
    )

    first_result = adapter.read_card()
    second_result = adapter.read_card()

    assert first_result.ok is True
    assert first_result.status is HardwareOperationStatus.SUCCESS
    assert first_result.uid == "0123456789ABCD"
    assert first_result.is_duplicate is False
    assert second_result.uid == "0123456789ABCD"
    assert second_result.is_duplicate is True
    assert adapter._transport.read_card_calls == [1000, 1000]


def test_real_rfid_adapter_read_card_reports_no_card_without_error() -> None:
    adapter = RealRfidAdapter(config=_rfid_config(), transport=_FakeStatusTransport(read_results=[None]))

    result = adapter.read_card()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.NO_CARD
    assert result.uid is None
    assert result.is_duplicate is False
    assert "No RFID card present" in (result.message or "")


def test_real_rfid_adapter_clear_buffer_is_intentionally_not_implemented_in_real_provider() -> None:
    adapter = RealRfidAdapter(config=_rfid_config(), transport=_FakeStatusTransport())

    with pytest.raises(HardwareProtocolNotImplementedError, match="buffer clear is intentionally not implemented"):
        adapter.clear_buffer()


def test_real_rfid_adapter_timeout_is_reported_as_safe_timeout() -> None:
    adapter = RealRfidAdapter(config=_rfid_config(), transport=_RaisingTransport(TimeoutError("timed out")))

    with pytest.raises(HardwareTimeoutError, match="timed out"):
        adapter.ping()

    with pytest.raises(HardwareTimeoutError, match="timed out"):
        adapter.read_card()


def test_real_provider_composition_accepts_minimal_rfid_config_and_operational_status_transport() -> None:
    settings = AppSettings(
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _serial_endpoint_config(code="lock-1", driver_name="lock-driver", port="COM2"),
            "rfid_reader": _minimal_rfid_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="/dev/ttyACM0"),
        },
    )

    bundle = create_hardware_bundle(
        settings,
        transport_overrides={"rfid_reader": _FakeStatusTransport()},
    )

    ping_result = bundle.rfid_reader.ping()

    assert bundle.provider is HardwareProvider.REAL
    assert isinstance(bundle.rfid_reader._transport, _FakeStatusTransport)
    assert ping_result.ok is True


def test_rusguard_acm_status_transport_uses_proven_status_sequence_on_selected_serial_endpoint() -> None:
    sdk = _FakeRusGuardSdk(endpoints=["/dev/ttyUSB0", "/dev/ttyACM0"])
    transport = RusGuardAcmStatusTransport(
        settings=_rfid_config().transport,
        timeouts=_rfid_config().endpoint.timeouts,
        sdk_loader=lambda _override: sdk,
    )

    transport.ping()

    assert sdk.calls == [
        "RG_InitializeLib",
        ("RG_FindEndPoints", 2),
        ("RG_GetFoundEndPointInfo", 0),
        ("RG_GetFoundEndPointInfo", 1),
        ("RG_InitDevice", "/dev/ttyACM0", 0),
        ("RG_GetStatus", "/dev/ttyACM0", 0),
        ("RG_CloseDevice", "/dev/ttyACM0", 0),
        ("RG_CloseResource", 1234),
        "RG_Uninitialize",
    ]


def test_rusguard_acm_status_transport_reads_card_without_cards_mask_on_selected_serial_endpoint() -> None:
    sdk = _FakeRusGuardSdk(
        endpoints=["/dev/ttyUSB0", "/dev/ttyACM0"],
        status_type=9,
        card_uid=bytes.fromhex("01 23 45 67 89 AB CD"),
    )
    transport = RusGuardAcmStatusTransport(
        settings=_rfid_config().transport,
        timeouts=_rfid_config().endpoint.timeouts,
        sdk_loader=lambda _override: sdk,
    )

    uid = transport.read_card()

    assert uid == bytes.fromhex("01 23 45 67 89 AB CD")
    assert sdk.calls == [
        "RG_InitializeLib",
        ("RG_FindEndPoints", 2),
        ("RG_GetFoundEndPointInfo", 0),
        ("RG_GetFoundEndPointInfo", 1),
        ("RG_InitDevice", "/dev/ttyACM0", 0),
        ("RG_GetStatus", "/dev/ttyACM0", 0, 9, "0123456789ABCD"),
        ("RG_CloseDevice", "/dev/ttyACM0", 0),
        ("RG_CloseResource", 1234),
        "RG_Uninitialize",
    ]


def test_rusguard_acm_status_transport_read_card_returns_none_when_reader_reports_no_card() -> None:
    sdk = _FakeRusGuardSdk(endpoints=["/dev/ttyACM0"], status_type=1)
    transport = RusGuardAcmStatusTransport(
        settings=_rfid_config().transport,
        timeouts=_rfid_config().endpoint.timeouts,
        sdk_loader=lambda _override: sdk,
    )

    uid = transport.read_card()

    assert uid is None


class _FakeStatusTransport:
    def __init__(self, *, read_results: list[bytes | None] | None = None) -> None:
        self.ping_calls: list[int | None] = []
        self.read_card_calls: list[int | None] = []
        self._read_results = list(read_results or [])

    def ping(self, *, timeout_ms: int | None = None) -> None:
        self.ping_calls.append(timeout_ms)

    def read_card(self, *, timeout_ms: int | None = None) -> bytes | None:
        self.read_card_calls.append(timeout_ms)
        if not self._read_results:
            return None
        return self._read_results.pop(0)


class _RaisingTransport:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def ping(self, *, timeout_ms: int | None = None) -> None:
        raise self._error

    def read_card(self, *, timeout_ms: int | None = None) -> bytes | None:
        raise self._error


class _FakeRusGuardSdk:
    def __init__(
        self,
        *,
        endpoints: list[str],
        status_type: int = 1,
        card_uid: bytes = b"\x00\x00\x00\x00\x00\x00\x00",
    ) -> None:
        self._endpoints = endpoints
        self._status_type = status_type
        self._card_uid = card_uid
        self.calls: list[object] = []

    def RG_InitializeLib(self) -> int:
        self.calls.append("RG_InitializeLib")
        return 0

    def RG_FindEndPoints(self, handle_ptr, endpoint_type_mask: int, count_ptr) -> int:
        self.calls.append(("RG_FindEndPoints", endpoint_type_mask))
        _set_pointer_value(handle_ptr, ctypes.c_void_p, 1234)
        _set_pointer_value(count_ptr, ctypes.c_uint32, len(self._endpoints))
        return 0

    def RG_GetFoundEndPointInfo(self, _handle, index: int, endpoint_info_ptr) -> int:
        self.calls.append(("RG_GetFoundEndPointInfo", index))
        endpoint_info = ctypes.cast(endpoint_info_ptr, ctypes.POINTER(_RgEndpointInfo)).contents
        endpoint_info.type = 2
        endpoint_info.address = self._endpoints[index].encode("ascii")
        endpoint_info.friendly_name = f"Friendly {index}".encode("ascii")
        return 0

    def RG_InitDevice(self, endpoint_ptr, address: int) -> int:
        self.calls.append(("RG_InitDevice", _endpoint_address(endpoint_ptr), address))
        return 0

    def RG_GetStatus(self, endpoint_ptr, address: int, status_ptr, _pin_states, card_info_ptr, _memory) -> int:
        status_value = ctypes.cast(status_ptr, ctypes.POINTER(ctypes.c_uint8))
        status_value.contents.value = self._status_type
        if card_info_ptr:
            card_info = ctypes.cast(card_info_ptr, ctypes.POINTER(_RgCardInfo)).contents
            card_info.type = 0
            card_info.uid = (ctypes.c_uint8 * 7).from_buffer_copy(self._card_uid)
            self.calls.append(
                ("RG_GetStatus", _endpoint_address(endpoint_ptr), address, self._status_type, self._card_uid.hex().upper())
            )
            return 0
        self.calls.append(("RG_GetStatus", _endpoint_address(endpoint_ptr), address))
        return 0

    def RG_CloseDevice(self, endpoint_ptr, address: int) -> int:
        self.calls.append(("RG_CloseDevice", _endpoint_address(endpoint_ptr), address))
        return 0

    def RG_CloseResource(self, handle) -> int:
        self.calls.append(("RG_CloseResource", handle.value))
        return 0

    def RG_Uninitialize(self) -> int:
        self.calls.append("RG_Uninitialize")
        return 0


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


def _set_pointer_value(pointer, ctype, value: int) -> None:
    ctypes.cast(pointer, ctypes.POINTER(ctype)).contents.value = value


def _endpoint_address(endpoint_ptr) -> str:
    endpoint = ctypes.cast(endpoint_ptr, ctypes.POINTER(type(endpoint_ptr._obj))).contents
    return endpoint.address.decode("ascii")
