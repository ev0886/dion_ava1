from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


_DEFAULT_LIBRARY_PATH = Path(__file__).resolve().parents[2] / "vendor" / "rusguard" / "sdk" / "librgsec.so"
_LIBRARY_PATH_ENV_VAR = "DION_RUSGUARD_SDK_LIBRARY_PATH"
# These endpoint type ids are isolated to this diagnostic path. The repo does not
# include vendor headers/docs proving the enum values, so they are used here as
# explicit discovery-testing assumptions only.
_DIAGNOSTIC_ET_SERIAL = 1
_DIAGNOSTIC_ET_USBHID = 2


class RusGuardSdkError(RuntimeError):
    pass


class MissingRusGuardAbiContractError(RusGuardSdkError):
    pass


@dataclass(frozen=True, slots=True)
class EnumeratedEndpoint:
    index: int
    type_name: str
    address: str
    friendly_name: str


@dataclass(frozen=True, slots=True)
class EnumeratedEndpointGroup:
    queried_type: str
    count: int
    endpoints: tuple[EnumeratedEndpoint, ...]
    endpoint_info_supported: bool = True
    unsupported_reason: str | None = None


@dataclass(frozen=True, slots=True)
class EndpointTypeContract:
    usb_hid: int
    serial: int


@dataclass(frozen=True, slots=True)
class EndpointInfoContract:
    structure_name: str


@dataclass(frozen=True, slots=True)
class VendorAbiContract:
    endpoint_types: EndpointTypeContract
    endpoint_info: EndpointInfoContract | None


class RusGuardSdkProtocol(Protocol):
    library_path: Path

    def initialize(self) -> None: ...

    def find_endpoints(self, endpoint_type: int) -> int: ...

    def get_found_endpoint_info(self, endpoint_type_name: str, index: int) -> EnumeratedEndpoint: ...

    def uninitialize(self) -> None: ...


@dataclass(frozen=True, slots=True)
class _EndpointQuery:
    label: str
    value: int


class CountOnlyRusGuardSdk:
    def __init__(self, library_path: Path) -> None:
        self.library_path = library_path
        try:
            self._library = ctypes.CDLL(str(library_path))
        except OSError as error:
            raise RusGuardSdkError(f"failed to load SDK library: {library_path}") from error

        self._library.RG_InitializeLib.argtypes = []
        self._library.RG_InitializeLib.restype = ctypes.c_int
        self._library.RG_FindEndPoints.argtypes = [ctypes.c_int]
        self._library.RG_FindEndPoints.restype = ctypes.c_int
        self._library.RG_Uninitialize.argtypes = []
        self._library.RG_Uninitialize.restype = ctypes.c_int

    def initialize(self) -> None:
        result = int(self._library.RG_InitializeLib())
        if result != 0:
            raise RusGuardSdkError(f"RG_InitializeLib failed with code {result}")

    def find_endpoints(self, endpoint_type: int) -> int:
        result = int(self._library.RG_FindEndPoints(endpoint_type))
        if result < 0:
            raise RusGuardSdkError(f"RG_FindEndPoints failed for type {endpoint_type} with code {result}")
        return result

    def get_found_endpoint_info(self, endpoint_type_name: str, index: int) -> EnumeratedEndpoint:
        raise MissingRusGuardAbiContractError(
            "endpoint info decoding unsupported due to missing vendor ABI contract for RG_GetFoundEndPointInfo"
        )

    def uninitialize(self) -> None:
        try:
            self._library.RG_Uninitialize()
        except Exception:
            return None
        return None


def run_rusguard_sdk_enumeration_command(*, library_path: str | None = None) -> int:
    resolved_library_path = resolve_library_path(library_path)
    try:
        contract = load_vendor_abi_contract()
        sdk = CountOnlyRusGuardSdk(resolved_library_path)
        groups = enumerate_endpoints(sdk, contract)
    except RusGuardSdkError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(render_report(resolved_library_path, groups))
    return 0


def resolve_library_path(library_path: str | None) -> Path:
    raw_path = library_path or os.environ.get(_LIBRARY_PATH_ENV_VAR) or str(_DEFAULT_LIBRARY_PATH)
    return Path(raw_path).expanduser().resolve()


def load_vendor_abi_contract() -> VendorAbiContract:
    return VendorAbiContract(
        endpoint_types=EndpointTypeContract(
            usb_hid=_DIAGNOSTIC_ET_USBHID,
            serial=_DIAGNOSTIC_ET_SERIAL,
        ),
        endpoint_info=None,
    )


def enumerate_endpoints(
    sdk: RusGuardSdkProtocol,
    contract: VendorAbiContract,
) -> tuple[EnumeratedEndpointGroup, ...]:
    queries = (
        _EndpointQuery(label="USB_HID", value=contract.endpoint_types.usb_hid),
        _EndpointQuery(label="SERIAL", value=contract.endpoint_types.serial),
    )
    sdk.initialize()
    try:
        groups = []
        for query in queries:
            count = sdk.find_endpoints(query.value)
            if count == 0:
                groups.append(
                    EnumeratedEndpointGroup(
                        queried_type=query.label,
                        count=0,
                        endpoints=(),
                    )
                )
                continue

            if contract.endpoint_info is None:
                groups.append(
                    EnumeratedEndpointGroup(
                        queried_type=query.label,
                        count=count,
                        endpoints=(),
                        endpoint_info_supported=False,
                        unsupported_reason=(
                            "endpoint info decoding unsupported due to missing vendor ABI contract"
                        ),
                    )
                )
                continue

            endpoints = tuple(sdk.get_found_endpoint_info(query.label, index) for index in range(count))
            groups.append(
                EnumeratedEndpointGroup(
                    queried_type=query.label,
                    count=count,
                    endpoints=endpoints,
                )
            )
        return tuple(groups)
    finally:
        sdk.uninitialize()


def render_report(library_path: Path, groups: tuple[EnumeratedEndpointGroup, ...]) -> str:
    lines = [
        "RusGuard SDK",
        f"library: {library_path.as_posix()}",
        "",
    ]
    for position, group in enumerate(groups):
        lines.append(f"[{group.queried_type}]")
        lines.append(f"count: {group.count}")
        for endpoint in group.endpoints:
            lines.append(
                f"- index: {endpoint.index}, type: {endpoint.type_name}, address: {endpoint.address}, "
                f"friendly_name: {endpoint.friendly_name}"
            )
        if group.endpoint_info_supported is False and group.unsupported_reason is not None:
            lines.append(group.unsupported_reason)
        if position != len(groups) - 1:
            lines.append("")
    return "\n".join(lines)
