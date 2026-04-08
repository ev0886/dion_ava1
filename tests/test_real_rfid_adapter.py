from __future__ import annotations

import ctypes
import struct
from pathlib import Path

import pytest

from app.config import AppSettings, HardwareProvider
from app.hardware import (
    CtypesRusGuardSdkClient,
    HardwareFailureError,
    HardwareOperationStatus,
    HardwareTimeoutError,
    HardwareUnavailableError,
    LinuxInputEventTransport,
    RealRfidAdapter,
    RusGuardSdkRead,
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
                _event_chunk(1, 42, 1),
                _event_chunk(1, 18, 1),
                _event_chunk(1, 18, 0),
                _event_chunk(1, 42, 0),
                _event_chunk(1, 3, 1),
                _event_chunk(1, 3, 0),
                _event_chunk(1, 8, 1),
                _event_chunk(1, 8, 0),
                _event_chunk(1, 7, 1),
                _event_chunk(1, 7, 0),
                _event_chunk(1, 8, 1),
                _event_chunk(1, 8, 0),
                _event_chunk(1, 42, 1),
                _event_chunk(1, 46, 1),
                _event_chunk(1, 46, 0),
                _event_chunk(1, 42, 0),
                _event_chunk(1, 11, 1),
                _event_chunk(1, 11, 0),
                _event_chunk(1, 11, 1),
                _event_chunk(1, 11, 0),
                _event_chunk(1, 5, 1),
                _event_chunk(1, 5, 0),
                _event_chunk(1, 6, 1),
                _event_chunk(1, 6, 0),
                _event_chunk(1, 28, 1),
                _event_chunk(1, 28, 0),
            ]
        ),
    )

    result = adapter.read_card()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert result.uid == "E2767C0045"
    assert result.is_duplicate is False


def test_real_rfid_adapter_reads_shifted_hex_linux_input_sequence_from_evtest_capture() -> None:
    adapter = RealRfidAdapter(
        config=_linux_input_rfid_config(),
        transport=_linux_input_transport(
            [
                _event_chunk(1, 42, 1),
                _event_chunk(1, 18, 1),
                _event_chunk(1, 18, 0),
                _event_chunk(1, 42, 0),
                _event_chunk(1, 3, 1),
                _event_chunk(1, 3, 0),
                _event_chunk(1, 8, 1),
                _event_chunk(1, 8, 0),
                _event_chunk(1, 7, 1),
                _event_chunk(1, 7, 0),
                _event_chunk(1, 8, 1),
                _event_chunk(1, 8, 0),
                _event_chunk(1, 42, 1),
                _event_chunk(1, 46, 1),
                _event_chunk(1, 46, 0),
                _event_chunk(1, 42, 0),
                _event_chunk(1, 11, 1),
                _event_chunk(1, 11, 0),
                _event_chunk(1, 11, 1),
                _event_chunk(1, 11, 0),
                _event_chunk(1, 5, 1),
                _event_chunk(1, 5, 0),
                _event_chunk(1, 6, 1),
                _event_chunk(1, 6, 0),
                _event_chunk(1, 28, 1),
                _event_chunk(1, 28, 0),
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


def test_real_rfid_adapter_reads_live_like_linux_input_sequence_with_recoverable_prefix_noise() -> None:
    transport = _StatefulLinuxInputTransport(
        stale_chunks=[],
        read_chunks=[
            _event_chunk(1, 59, 1),
            _event_chunk(1, 57, 1),
            _event_chunk(0, 0, 0),
            _event_chunk(1, 18, 1),
            _event_chunk(1, 18, 0),
            _event_chunk(1, 3, 1),
            _event_chunk(1, 3, 0),
            _event_chunk(1, 57, 1),
            _event_chunk(1, 57, 0),
            _event_chunk(1, 8, 1),
            _event_chunk(1, 8, 0),
            _event_chunk(1, 12, 1),
            _event_chunk(1, 12, 0),
            _event_chunk(1, 7, 1),
            _event_chunk(1, 7, 0),
            _event_chunk(1, 8, 1),
            _event_chunk(1, 8, 0),
            _event_chunk(1, 46, 1),
            _event_chunk(1, 46, 0),
            _event_chunk(1, 96, 1),
        ],
    )
    adapter = RealRfidAdapter(config=_linux_input_rfid_config(), transport=transport)

    result = adapter.read_card()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert result.uid == "E2767C"
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
    transport = _StatefulLinuxInputTransport(
        stale_chunks=[],
        read_chunks=[_event_chunk(1, 18, 1), _event_chunk(1, 3, 1)],
        read_readable_sequence=[True, True, False],
    )
    adapter = RealRfidAdapter(config=_linux_input_rfid_config(), transport=transport)

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
    transport = _StatefulLinuxInputTransport(stale_chunks=[], read_chunks=[_event_chunk(1, 59, 1)])
    adapter = RealRfidAdapter(config=_linux_input_rfid_config(), transport=transport)

    with pytest.raises(HardwareFailureError, match="unsupported read response"):
        adapter.read_card()


def test_real_rfid_adapter_clears_stale_linux_input_buffer_before_reading_next_card() -> None:
    transport = _StatefulLinuxInputTransport(
        stale_chunks=[
            _event_chunk(1, 16, 1),
            _event_chunk(1, 17, 1),
            _event_chunk(1, 28, 1),
        ],
        read_chunks=[
            _event_chunk(1, 18, 1),
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
        ],
    )
    adapter = RealRfidAdapter(config=_linux_input_rfid_config(), transport=transport)

    result = adapter.read_card()

    assert result.ok is True
    assert result.uid == "E2767C0045"
    assert transport.clear_calls == 1


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


def test_real_rfid_adapter_reads_uid_from_rusguard_sdk_client() -> None:
    adapter = RealRfidAdapter(
        config=_sdk_rfid_config(),
        transport=None,
        sdk_client=_FakeSdkClient([RusGuardSdkRead(uid="E2 76-7C 00 45")]),
    )

    result = adapter.read_card()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.SUCCESS
    assert result.uid == "E2767C0045"
    assert result.is_duplicate is False


def test_real_rfid_adapter_maps_no_card_from_rusguard_sdk_client() -> None:
    adapter = RealRfidAdapter(
        config=_sdk_rfid_config(),
        transport=None,
        sdk_client=_FakeSdkClient([RusGuardSdkRead(uid=None, no_card=True)]),
    )

    result = adapter.read_card()

    assert result.ok is True
    assert result.status is HardwareOperationStatus.NO_CARD
    assert result.uid is None


def test_real_rfid_adapter_surfaces_sdk_failures_at_adapter_boundary() -> None:
    adapter = RealRfidAdapter(
        config=_sdk_rfid_config(),
        transport=None,
        sdk_client=_FakeSdkClient([OSError("sdk status failed")]),
    )

    with pytest.raises(HardwareFailureError, match="sdk status failed"):
        adapter.read_card()


def test_ctypes_rusguard_sdk_client_reads_uid_via_vendor_status_flow() -> None:
    library = _FakeRusGuardSdkLibrary(status_sequence=[{"status": 26, "uid": bytes.fromhex("E2 76 7C 00 45 00 00")}])
    client = CtypesRusGuardSdkClient(
        library_path=_existing_fake_library_path(),
        endpoint_type="usb_hid",
        device_index=0,
        device_address=0,
        library_loader=lambda path: library,
    )

    result = client.read_uid()

    assert result == RusGuardSdkRead(uid="E2767C00450000")
    assert library.find_masks == [1]
    assert library.init_device_calls == [{"address": 0, "endpoint_type": 1, "endpoint_address": "hid://reader-0"}]
    assert library.set_cards_mask_calls == [{"address": 0, "mask": 255}]
    assert library.close_device_calls == [{"address": 0, "endpoint_address": "hid://reader-0"}]
    assert library.initialize_calls == 1
    assert library.uninitialize_calls == 1


def test_ctypes_rusguard_sdk_client_maps_no_card_from_vendor_status() -> None:
    library = _FakeRusGuardSdkLibrary(status_sequence=[{"status": 1, "uid": bytes(7)}])
    client = CtypesRusGuardSdkClient(
        library_path=_existing_fake_library_path(),
        endpoint_type="usb_hid",
        library_loader=lambda path: library,
    )

    result = client.read_uid()

    assert result == RusGuardSdkRead(uid=None, no_card=True)


def test_ctypes_rusguard_sdk_client_raises_on_vendor_error() -> None:
    library = _FakeRusGuardSdkLibrary(get_status_error=12)
    client = CtypesRusGuardSdkClient(
        library_path=_existing_fake_library_path(),
        endpoint_type="usb_hid",
        library_loader=lambda path: library,
    )

    with pytest.raises(OSError, match=r"RG_GetStatus failed with EC_DEVICE_COMM_FAILURE \(12\)"):
        client.read_uid()


def test_real_provider_composition_supports_rusguard_sdk_rfid_transport() -> None:
    settings = AppSettings(
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _lock_serial_endpoint_config(code="lock-1", driver_name="lock-driver", port="COM2"),
            "rfid_reader": _sdk_endpoint_config(
                code="rfid-1",
                driver_name="rusguard-sdk-usbhid",
                library_path="/opt/dion_ava1/vendor/rusguard/linux_arm64_release/librgsec.so",
            ),
        },
    )

    bundle = create_hardware_bundle(settings)

    assert bundle.provider is HardwareProvider.REAL
    assert isinstance(bundle.rfid_reader, RealRfidAdapter)


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


class _FakeSdkClient:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.read_timeouts: list[int | None] = []

    def ping(self) -> None:
        return None

    def read_uid(self, *, timeout_ms: int | None = None) -> RusGuardSdkRead:
        self.read_timeouts.append(timeout_ms)
        if not self._responses:
            raise AssertionError("No fake SDK responses remain.")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response  # type: ignore[return-value]


class _FunctionStub:
    def __init__(self, callback) -> None:
        self._callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self._callback(*args)


class _FakeRusGuardSdkLibrary:
    def __init__(
        self,
        *,
        status_sequence: list[dict[str, object]] | None = None,
        find_endpoints_error: int = 0,
        init_device_error: int = 0,
        set_cards_mask_error: int = 0,
        get_status_error: int = 0,
    ) -> None:
        self._status_sequence = list(status_sequence or [])
        self._find_endpoints_error = find_endpoints_error
        self._init_device_error = init_device_error
        self._set_cards_mask_error = set_cards_mask_error
        self._get_status_error = get_status_error
        self.initialize_calls = 0
        self.uninitialize_calls = 0
        self.find_masks: list[int] = []
        self.closed_resources: list[int | None] = []
        self.init_device_calls: list[dict[str, object]] = []
        self.set_cards_mask_calls: list[dict[str, object]] = []
        self.close_device_calls: list[dict[str, object]] = []
        self.endpoint_addresses = [b"hid://reader-0"]

        self.RG_InitializeLib = _FunctionStub(self._rg_initialize_lib)
        self.RG_Uninitialize = _FunctionStub(self._rg_uninitialize)
        self.RG_CloseResource = _FunctionStub(self._rg_close_resource)
        self.RG_FindEndPoints = _FunctionStub(self._rg_find_endpoints)
        self.RG_GetFoundEndPointInfo = _FunctionStub(self._rg_get_found_endpoint_info)
        self.RG_InitDevice = _FunctionStub(self._rg_init_device)
        self.RG_SetCardsMask = _FunctionStub(self._rg_set_cards_mask)
        self.RG_GetStatus = _FunctionStub(self._rg_get_status)
        self.RG_CloseDevice = _FunctionStub(self._rg_close_device)

    def _rg_initialize_lib(self) -> int:
        self.initialize_calls += 1
        return 0

    def _rg_uninitialize(self) -> int:
        self.uninitialize_calls += 1
        return 0

    def _rg_close_resource(self, handle) -> int:
        self.closed_resources.append(getattr(handle, "value", handle))
        return 0

    def _rg_find_endpoints(self, handle_ptr, endpoint_mask: int, count_ptr) -> int:
        self.find_masks.append(endpoint_mask)
        if self._find_endpoints_error:
            return self._find_endpoints_error
        ctypes.cast(handle_ptr, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(1234)
        ctypes.cast(count_ptr, ctypes.POINTER(ctypes.c_uint32))[0] = ctypes.c_uint32(len(self.endpoint_addresses))
        return 0

    def _rg_get_found_endpoint_info(self, handle, list_index: int, endpoint_info_ptr) -> int:
        endpoint_info = ctypes.cast(endpoint_info_ptr, ctypes.POINTER(_sdk_endpoint_info_type())).contents
        address = self.endpoint_addresses[list_index]
        endpoint_info.type = 1
        endpoint_info.address = address  # type: ignore[assignment]
        endpoint_info.friendly_name = b"RusGuard R5 USB"  # type: ignore[assignment]
        return 0

    def _rg_init_device(self, endpoint_ptr, device_address: int) -> int:
        endpoint = ctypes.cast(endpoint_ptr, ctypes.POINTER(_sdk_endpoint_type())).contents
        self.init_device_calls.append(
            {
                "address": device_address,
                "endpoint_type": endpoint.type,
                "endpoint_address": ctypes.string_at(endpoint.address).decode("ascii"),
            }
        )
        return self._init_device_error

    def _rg_set_cards_mask(self, endpoint_ptr, device_address: int, cards_mask: int) -> int:
        self.set_cards_mask_calls.append({"address": device_address, "mask": cards_mask})
        return self._set_cards_mask_error

    def _rg_get_status(self, endpoint_ptr, device_address: int, status_ptr, pin_states_ptr, card_info_ptr, memory_ptr) -> int:
        if self._get_status_error:
            return self._get_status_error
        if not self._status_sequence:
            raise AssertionError("No fake RusGuard status responses remain.")
        status_entry = self._status_sequence.pop(0)
        ctypes.cast(status_ptr, ctypes.POINTER(ctypes.c_uint8))[0] = ctypes.c_uint8(status_entry["status"])
        card_info = ctypes.cast(card_info_ptr, ctypes.POINTER(_sdk_card_info_type())).contents
        card_info.type = 9
        uid = status_entry["uid"]
        for index, byte in enumerate(uid):
            card_info.uid[index] = byte
        return 0

    def _rg_close_device(self, endpoint_ptr, device_address: int) -> int:
        endpoint = ctypes.cast(endpoint_ptr, ctypes.POINTER(_sdk_endpoint_type())).contents
        self.close_device_calls.append(
            {
                "address": device_address,
                "endpoint_address": ctypes.string_at(endpoint.address).decode("ascii"),
            }
        )
        return 0


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


class _StatefulLinuxInputTransport(LinuxInputEventTransport):
    def __init__(
        self,
        *,
        stale_chunks: list[bytes],
        read_chunks: list[bytes],
        clear_readable_sequence: list[bool] | None = None,
        read_readable_sequence: list[bool] | None = None,
    ) -> None:
        self.clear_calls = 0
        self._clear_device = _FakeInputDevice(stale_chunks, readable_sequence=clear_readable_sequence)
        self._read_device = _FakeInputDevice(read_chunks, readable_sequence=read_readable_sequence)
        super().__init__(
            settings=LinuxInputTransportSettings(transport="linux_input", device_path="/dev/input/event7"),
            timeouts=EndpointTimeoutSettings(connect_timeout_ms=1000, read_timeout_ms=1000, write_timeout_ms=1000),
            device_opener=self._open_device,
        )

    def _open_device(self, device_path: str, nonblocking: bool) -> _FakeInputDevice:
        if self.clear_calls == 0:
            self.clear_calls += 1
            return self._clear_device
        return self._read_device


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


def _sdk_rfid_config() -> RfidHardwareEndpointTransportConfig:
    return RfidHardwareEndpointTransportConfig.model_validate(
        _sdk_endpoint_config(
            code="rfid-1",
            driver_name="rusguard-sdk-usbhid",
            library_path="/opt/dion_ava1/vendor/rusguard/linux_arm64_release/librgsec.so",
        )
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


def _sdk_endpoint_config(*, code: str, driver_name: str, library_path: str) -> dict[str, object]:
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
            "transport": "sdk",
            "library_path": library_path,
            "endpoint_type": "usb_hid",
            "device_index": 0,
            "device_address": 0,
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


def _existing_fake_library_path() -> str:
    return str(Path(__file__))


def _sdk_endpoint_info_type():
    return CtypesRusGuardSdkClient._resolve_endpoint.__globals__["_RG_ENDPOINT_INFO"]


def _sdk_endpoint_type():
    return CtypesRusGuardSdkClient._resolve_endpoint.__globals__["_RG_ENDPOINT"]


def _sdk_card_info_type():
    return CtypesRusGuardSdkClient._resolve_endpoint.__globals__["_RG_CARD_INFO"]

