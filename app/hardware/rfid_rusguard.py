from __future__ import annotations

import ctypes
import ctypes.util
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Final, Protocol, runtime_checkable

from app.hardware.transport_config import EndpointTimeoutSettings, RfidSerialTransportSettings


@runtime_checkable
class RfidStatusTransport(Protocol):
    def ping(self, *, timeout_ms: int | None = None) -> None: ...

    def read_card(self, *, timeout_ms: int | None = None) -> "RusGuardCardRead": ...


@dataclass(frozen=True, slots=True)
class RusGuardCardRead:
    status_type: int
    uid: str | None
    uid_size: int


class RusGuardAcmStatusTransport:
    _ENDPOINT_TYPE_SERIAL: Final[int] = 0x02
    _DEVICE_ADDRESS: Final[int] = 0
    _STATUS_NO_CARD: Final[int] = 0x01
    _GET_CARD_UID_BUFFER_SIZE: Final[int] = 64
    _LIBRARY_CANDIDATES: Final[tuple[str, ...]] = (
        "rg",
        "rusguard",
        "librg.so",
        "librusguard.so",
        "RG.dll",
        "rusguard.dll",
    )

    def __init__(
        self,
        *,
        settings: RfidSerialTransportSettings,
        timeouts: EndpointTimeoutSettings,
        sdk_loader: Callable[[str | None], object] | None = None,
    ) -> None:
        self._settings = settings
        self._timeouts = timeouts
        self._sdk_loader = sdk_loader or _load_rusguard_sdk

    def ping(self, *, timeout_ms: int | None = None) -> None:
        del timeout_ms
        sdk = self._sdk_loader(self._settings.sdk_library)
        with _open_selected_device(sdk=sdk, port=self._settings.port) as endpoint:
            status_type = ctypes.c_uint8()
            _check_sdk_error(
                sdk.RG_GetStatus(
                    ctypes.byref(endpoint),
                    self._DEVICE_ADDRESS,
                    ctypes.byref(status_type),
                    None,
                    None,
                    None,
                ),
                "RG_GetStatus",
            )

    def read_card(self, *, timeout_ms: int | None = None) -> RusGuardCardRead:
        del timeout_ms
        sdk = self._sdk_loader(self._settings.sdk_library)
        with _open_selected_device(sdk=sdk, port=self._settings.port) as endpoint:
            status_type = ctypes.c_uint8()
            uid_size = ctypes.c_int32()
            uid_buffer = (ctypes.c_uint8 * self._GET_CARD_UID_BUFFER_SIZE)()
            _check_sdk_error(
                sdk.RG_GetCard(
                    ctypes.byref(endpoint),
                    self._DEVICE_ADDRESS,
                    ctypes.byref(status_type),
                    uid_buffer,
                    self._GET_CARD_UID_BUFFER_SIZE,
                    ctypes.byref(uid_size),
                ),
                "RG_GetCard",
            )
            resolved_uid_size = uid_size.value
            if resolved_uid_size < 0 or resolved_uid_size > self._GET_CARD_UID_BUFFER_SIZE:
                raise OSError(
                    f"RG_GetCard returned invalid UID size {resolved_uid_size} "
                    f"for buffer size {self._GET_CARD_UID_BUFFER_SIZE}."
                )
            if status_type.value == self._STATUS_NO_CARD or resolved_uid_size == 0:
                return RusGuardCardRead(status_type=status_type.value, uid=None, uid_size=resolved_uid_size)
            return RusGuardCardRead(
                status_type=status_type.value,
                uid=_bytes_to_hex(uid_buffer, resolved_uid_size),
                uid_size=resolved_uid_size,
            )


class _RusGuardSession:
    def __init__(self, *, sdk: object, port: str) -> None:
        self._sdk = sdk
        self._port = port
        self._endpoint_list_handle = ctypes.c_void_p()
        self._initialized = False
        self.endpoint: _RgEndpoint | None = None

    def __enter__(self) -> _RgEndpoint:
        endpoint_count = ctypes.c_uint32()
        _check_sdk_error(self._sdk.RG_InitializeLib(), "RG_InitializeLib")
        self._initialized = True
        try:
            _check_sdk_error(
                self._sdk.RG_FindEndPoints(
                    ctypes.byref(self._endpoint_list_handle),
                    RusGuardAcmStatusTransport._ENDPOINT_TYPE_SERIAL,
                    ctypes.byref(endpoint_count),
                ),
                "RG_FindEndPoints",
            )
            self.endpoint = _select_serial_endpoint(
                sdk=self._sdk,
                endpoint_list_handle=self._endpoint_list_handle,
                endpoint_count=endpoint_count.value,
                port=self._port,
            )
            _check_sdk_error(
                self._sdk.RG_InitDevice(ctypes.byref(self.endpoint), RusGuardAcmStatusTransport._DEVICE_ADDRESS),
                "RG_InitDevice",
            )
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self.endpoint

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.endpoint is not None:
            _check_sdk_error(
                self._sdk.RG_CloseDevice(ctypes.byref(self.endpoint), RusGuardAcmStatusTransport._DEVICE_ADDRESS),
                "RG_CloseDevice",
            )
        if self._endpoint_list_handle.value:
            _check_sdk_error(self._sdk.RG_CloseResource(self._endpoint_list_handle), "RG_CloseResource")
        if self._initialized:
            _check_sdk_error(self._sdk.RG_Uninitialize(), "RG_Uninitialize")


def _open_selected_device(*, sdk: object, port: str) -> _RusGuardSession:
    return _RusGuardSession(sdk=sdk, port=port)


class _RgEndpoint(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("type", ctypes.c_uint8), ("address", ctypes.c_char_p)]


class _RgEndpointInfo(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("type", ctypes.c_uint8),
        ("address", ctypes.c_char * 64),
        ("friendly_name", ctypes.c_char * 128),
    ]


def _select_serial_endpoint(
    *,
    sdk: object,
    endpoint_list_handle: ctypes.c_void_p,
    endpoint_count: int,
    port: str,
) -> _RgEndpoint:
    discovered_serial_ports: list[str] = []
    normalized_requested_port = port.strip()
    for endpoint_index in range(endpoint_count):
        endpoint_info = _RgEndpointInfo()
        _check_sdk_error(
            sdk.RG_GetFoundEndPointInfo(endpoint_list_handle, endpoint_index, ctypes.byref(endpoint_info)),
            "RG_GetFoundEndPointInfo",
        )
        if endpoint_info.type != RusGuardAcmStatusTransport._ENDPOINT_TYPE_SERIAL:
            continue
        discovered_port = _decode_c_string(endpoint_info.address)
        discovered_serial_ports.append(discovered_port)
        if discovered_port == normalized_requested_port:
            return _RgEndpoint(type=endpoint_info.type, address=discovered_port.encode("ascii"))
    discovered = ", ".join(discovered_serial_ports) if discovered_serial_ports else "none"
    raise OSError(
        f"RusGuard serial endpoint {normalized_requested_port!r} was not found. "
        f"Discovered SERIAL endpoints: {discovered}."
    )


def _bytes_to_hex(data: ctypes.Array[ctypes.c_uint8], size: int) -> str:
    return bytes(data[:size]).hex().upper()


def _decode_c_string(raw_value: bytes | bytearray) -> str:
    return bytes(raw_value).split(b"\0", 1)[0].decode("ascii", errors="strict")


def _check_sdk_error(error_code: int, operation: str) -> None:
    if error_code != 0:
        raise OSError(f"{operation} failed with RusGuard SDK error code {error_code}.")


def _load_rusguard_sdk(override_path: str | None) -> ctypes.CDLL:
    load_errors: list[str] = []
    for candidate in _candidate_library_paths(override_path):
        try:
            return ctypes.CDLL(candidate)
        except OSError as error:
            load_errors.append(f"{candidate}: {error}")
    detail = "; ".join(load_errors) if load_errors else "no library candidates were found"
    raise OSError(f"RusGuard SDK library could not be loaded: {detail}.")


def _candidate_library_paths(override_path: str | None) -> tuple[str, ...]:
    candidates: list[str] = []
    if override_path is not None:
        candidates.append(override_path)
    for name in RusGuardAcmStatusTransport._LIBRARY_CANDIDATES:
        found = ctypes.util.find_library(name)
        if found is not None:
            candidates.append(found)
        candidates.append(name)
    repo_root = Path(__file__).resolve().parents[2]
    for local_name in ("librg.so", "librusguard.so", "RG.dll", "rusguard.dll"):
        candidates.append(str(repo_root / "vendor" / "rusguard" / "sdk" / local_name))
    deduped: list[str] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    return tuple(deduped)
