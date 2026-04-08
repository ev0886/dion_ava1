from __future__ import annotations

import ctypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


RUSGUARD_SDK_DRIVER_NAMES = frozenset({"rusguard-sdk", "rusguard-sdk-usbhid", "rusguard-r5-sdk-usbhid"})

_ET_USBHID = 1
_EC_OK = 0
_EC_INVALID_CONNECTION_ADDRESS = 7
_EC_CALL_INIT = 16
_EC_DEVICE_NO_CARD = 21
_STE_NO_CARD = 1
_STE_CARD = 9
_STE_CARD_NO_AUTH = 10
_STE_CARD_AUTH = 26
_CF_ALL = 255
_POLL_INTERVAL_SECONDS = 0.1
_UID_SIZE = 7

_ERROR_NAMES = {
    0: "EC_OK",
    1: "EC_FAIL",
    2: "EC_NOT_IMPLEMENTED",
    3: "EC_BAD_ARGUMENT",
    4: "EC_INVALID_HANDLE",
    5: "EC_INVALID_RESOURCE",
    6: "EC_INVALID_CONNECTION_TYPE",
    7: "EC_INVALID_CONNECTION_ADDRESS",
    8: "EC_INVALID_DEVICE_ADDRESS",
    9: "EC_DEVICE_OPERATION_UNSUPPORTED",
    10: "EC_DEVICE_NOT_CONNECTED",
    11: "EC_DEVICE_NO_RESPOND",
    12: "EC_DEVICE_COMM_FAILURE",
    13: "EC_DEVICE_PROTOCOL_FAILURE",
    14: "EC_POLL_NO_EVENTS",
    15: "EC_POLL_QUEUE_CLOSED",
    16: "EC_CALL_INIT",
    17: "EC_DEVICE_INVALID_COMMAND",
    18: "EC_DEVICE_INVALID_PARAM",
    19: "EC_DEVICE_INVALID_PIN",
    20: "EC_DEVICE_COMMAND_TIMEOUT",
    21: "EC_DEVICE_NO_CARD",
    22: "EC_DEVICE_UOWN_CARD",
    23: "EC_DEVICE_INCOMPATIBLE_CARD",
    24: "EC_DEVICE_AUTH_FAIL",
    25: "EC_DEVICE_PROFILE_FAIL",
    26: "EC_DEVICE_RW_FAIL",
    27: "EC_IO_OPEN_FAIL",
    28: "EC_IO_CLOSE_FAIL",
    29: "EC_IO_READ_FAIL",
    30: "EC_IO_WRITE_FAIL",
    31: "EC_IO_CLOSED",
    32: "EC_DEVICE_IN_BOOT",
    33: "EC_DEVICE_FW_INVALID_MODEL",
    34: "EC_FILE_NOT_FOUND",
    35: "EC_FINGERPRINT_UNFOUND",
}


class _RG_ENDPOINT(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("type", ctypes.c_uint8),
        ("address", ctypes.c_char_p),
    ]


class _RG_ENDPOINT_INFO(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("type", ctypes.c_uint8),
        ("address", ctypes.c_char * 64),
        ("friendly_name", ctypes.c_char * 128),
    ]


class _RG_CARD_INFO(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("type", ctypes.c_uint8),
        ("uid", ctypes.c_uint8 * _UID_SIZE),
    ]


@dataclass(frozen=True, slots=True)
class RusGuardSdkRead:
    uid: str | None
    no_card: bool = False


class RusGuardSdkClient(Protocol):
    def ping(self) -> None: ...

    def read_uid(self, *, timeout_ms: int | None = None) -> RusGuardSdkRead: ...


class CtypesRusGuardSdkClient:
    _REQUIRED_EXPORTS = (
        "RG_InitializeLib",
        "RG_Uninitialize",
        "RG_CloseResource",
        "RG_FindEndPoints",
        "RG_GetFoundEndPointInfo",
        "RG_InitDevice",
        "RG_SetCardsMask",
        "RG_GetStatus",
        "RG_CloseDevice",
    )

    def __init__(
        self,
        *,
        library_path: str,
        endpoint_type: str = "usb_hid",
        device_index: int = 0,
        device_address: int = 0,
        library_loader: Callable[[str], object] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._library_path = Path(library_path)
        self._endpoint_type = endpoint_type.strip().casefold()
        self._device_index = device_index
        self._device_address = device_address
        self._library_loader = library_loader or ctypes.CDLL
        self._sleep = sleep or time.sleep

    def ping(self) -> None:
        with self._session() as library:
            self._resolve_endpoint(library)

    def read_uid(self, *, timeout_ms: int | None = None) -> RusGuardSdkRead:
        with self._session() as library:
            endpoint, address_buffer = self._resolve_endpoint(library)
            self._init_device(library, endpoint)
            try:
                self._set_cards_mask(library, endpoint)
                deadline_monotonic = None
                if timeout_ms is not None:
                    deadline_monotonic = time.monotonic() + (timeout_ms / 1000)
                while True:
                    status = ctypes.c_uint8()
                    card_info = _RG_CARD_INFO()
                    error = library.RG_GetStatus(
                        ctypes.byref(endpoint),
                        self._device_address,
                        ctypes.byref(status),
                        None,
                        ctypes.byref(card_info),
                        None,
                    )
                    if error == _EC_OK:
                        if status.value == _STE_NO_CARD:
                            if deadline_monotonic is None:
                                return RusGuardSdkRead(uid=None, no_card=True)
                            if time.monotonic() >= deadline_monotonic:
                                raise TimeoutError("RusGuard SDK card read timed out.")
                            self._sleep(_POLL_INTERVAL_SECONDS)
                            continue
                        if status.value in {_STE_CARD, _STE_CARD_NO_AUTH, _STE_CARD_AUTH}:
                            uid_hex = bytes(card_info.uid).hex().upper()
                            if not uid_hex:
                                raise OSError("RusGuard SDK returned an empty card UID.")
                            return RusGuardSdkRead(uid=uid_hex)
                        raise OSError(f"RusGuard SDK returned unsupported status {status.value}.")
                    if error == _EC_DEVICE_NO_CARD:
                        if deadline_monotonic is None:
                            return RusGuardSdkRead(uid=None, no_card=True)
                        if time.monotonic() >= deadline_monotonic:
                            raise TimeoutError("RusGuard SDK card read timed out.")
                        self._sleep(_POLL_INTERVAL_SECONDS)
                        continue
                    if error == _EC_CALL_INIT:
                        raise OSError(self._format_error("RG_GetStatus", error))
                    raise OSError(self._format_error("RG_GetStatus", error))
            finally:
                self._close_device(library, endpoint)
                del address_buffer

    def _load_library(self) -> object:
        if not self._library_path.is_file():
            raise OSError(f"RusGuard SDK shared library was not found: {self._library_path}")
        library = self._library_loader(str(self._library_path))
        self._configure_library(library)
        return library

    def _configure_library(self, library: object) -> None:
        for export_name in self._REQUIRED_EXPORTS:
            if not hasattr(library, export_name):
                raise OSError(
                    f"RusGuard SDK library is missing required export {export_name!r}: {self._library_path}"
                )
        library.RG_InitializeLib.restype = ctypes.c_uint32
        library.RG_Uninitialize.restype = ctypes.c_uint32
        library.RG_CloseResource.argtypes = [ctypes.c_void_p]
        library.RG_CloseResource.restype = ctypes.c_uint32
        library.RG_FindEndPoints.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint8, ctypes.POINTER(ctypes.c_uint32)]
        library.RG_FindEndPoints.restype = ctypes.c_uint32
        library.RG_GetFoundEndPointInfo.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_RG_ENDPOINT_INFO)]
        library.RG_GetFoundEndPointInfo.restype = ctypes.c_uint32
        library.RG_InitDevice.argtypes = [ctypes.POINTER(_RG_ENDPOINT), ctypes.c_uint8]
        library.RG_InitDevice.restype = ctypes.c_uint32
        library.RG_SetCardsMask.argtypes = [ctypes.POINTER(_RG_ENDPOINT), ctypes.c_uint8, ctypes.c_uint8]
        library.RG_SetCardsMask.restype = ctypes.c_uint32
        library.RG_GetStatus.argtypes = [
            ctypes.POINTER(_RG_ENDPOINT),
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(_RG_CARD_INFO),
            ctypes.c_void_p,
        ]
        library.RG_GetStatus.restype = ctypes.c_uint32
        library.RG_CloseDevice.argtypes = [ctypes.POINTER(_RG_ENDPOINT), ctypes.c_uint8]
        library.RG_CloseDevice.restype = ctypes.c_uint32

    def _resolve_endpoint(self, library: object) -> tuple[_RG_ENDPOINT, ctypes.Array[ctypes.c_char]]:
        if self._endpoint_type != "usb_hid":
            raise OSError(f"RusGuard SDK endpoint_type {self._endpoint_type!r} is not supported in this MVP.")
        handle = ctypes.c_void_p()
        count = ctypes.c_uint32()
        error = library.RG_FindEndPoints(ctypes.byref(handle), _ET_USBHID, ctypes.byref(count))
        if error != _EC_OK:
            raise OSError(self._format_error("RG_FindEndPoints", error))
        try:
            if count.value <= self._device_index:
                raise OSError(
                    f"RusGuard SDK endpoint index {self._device_index} is out of range; found {count.value} USB HID endpoint(s)."
                )
            endpoint_info = _RG_ENDPOINT_INFO()
            error = library.RG_GetFoundEndPointInfo(handle, self._device_index, ctypes.byref(endpoint_info))
            if error != _EC_OK:
                raise OSError(self._format_error("RG_GetFoundEndPointInfo", error))
            address = bytes(endpoint_info.address).split(b"\0", 1)[0]
            if not address:
                raise OSError("RusGuard SDK returned an empty endpoint address.")
            address_buffer = ctypes.create_string_buffer(address)
            endpoint = _RG_ENDPOINT(type=endpoint_info.type, address=ctypes.cast(address_buffer, ctypes.c_char_p))
            return endpoint, address_buffer
        finally:
            library.RG_CloseResource(handle)

    def _init_device(self, library: object, endpoint: _RG_ENDPOINT) -> None:
        error = library.RG_InitDevice(ctypes.byref(endpoint), self._device_address)
        if error == _EC_INVALID_CONNECTION_ADDRESS:
            raise OSError(f"RusGuard SDK endpoint address {self._device_index} is invalid or not present.")
        if error != _EC_OK:
            raise OSError(self._format_error("RG_InitDevice", error))

    def _set_cards_mask(self, library: object, endpoint: _RG_ENDPOINT) -> None:
        error = library.RG_SetCardsMask(ctypes.byref(endpoint), self._device_address, _CF_ALL)
        if error != _EC_OK:
            raise OSError(self._format_error("RG_SetCardsMask", error))

    def _close_device(self, library: object, endpoint: _RG_ENDPOINT) -> None:
        error = library.RG_CloseDevice(ctypes.byref(endpoint), self._device_address)
        if error not in {_EC_OK, _EC_CALL_INIT}:
            raise OSError(self._format_error("RG_CloseDevice", error))

    def _format_error(self, function_name: str, error_code: int) -> str:
        error_name = _ERROR_NAMES.get(error_code, "UNKNOWN")
        return f"{function_name} failed with {error_name} ({error_code})."

    class _Session:
        def __init__(self, client: CtypesRusGuardSdkClient) -> None:
            self._client = client
            self._library: object | None = None

        def __enter__(self) -> object:
            library = self._client._load_library()
            error = library.RG_InitializeLib()
            if error != _EC_OK:
                raise OSError(self._client._format_error("RG_InitializeLib", error))
            self._library = library
            return library

        def __exit__(self, exc_type, exc, tb) -> None:
            if self._library is None:
                return
            error = self._library.RG_Uninitialize()
            if error != _EC_OK and exc is None:
                raise OSError(self._client._format_error("RG_Uninitialize", error))

    def _session(self) -> _Session:
        return self._Session(self)
