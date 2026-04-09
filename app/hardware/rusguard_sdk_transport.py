from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.diagnostics.rusguard_sdk import (
    CountOnlyRusGuardSdk,
    EndpointInfo,
    RG_ENDPOINT_TYPE_SERIAL,
    RusGuardSdkError,
    decode_api_error,
    resolve_library_path,
)

_PING_REQUEST = b"PING\n"
_PONG_RESPONSE = b"PONG\n"
_TARGET_ACM_ENDPOINT = "/dev/ttyACM0"


@dataclass(frozen=True, slots=True)
class RusGuardSdkAcmTransport:
    sdk_factory: Callable[[Path], CountOnlyRusGuardSdk] = CountOnlyRusGuardSdk
    library_path: Path | None = None
    target_endpoint: str = _TARGET_ACM_ENDPOINT

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        del timeout_ms
        if payload != _PING_REQUEST:
            raise NotImplementedError("RusGuard SDK RFID transport currently supports ping only.")

        sdk = self.sdk_factory(resolve_library_path(str(self.library_path) if self.library_path is not None else None))
        try:
            sdk.initialize()
            endpoint_info = self._select_target_endpoint(sdk.find_endpoint_infos(RG_ENDPOINT_TYPE_SERIAL))
            result = sdk.diagnose_acm_status_no_mask_endpoint(endpoint_info)
            if not result.open_result.ok:
                raise OSError(self._format_operation_error("RG_InitDevice", result.open_result.code))
            if result.status_result is None:
                raise OSError("RG_GetStatus was not attempted for the RusGuard ACM endpoint.")
            if not result.status_result.ok:
                raise OSError(self._format_operation_error("RG_GetStatus", result.status_result.code))
            if result.close_result is None:
                raise OSError("RG_CloseDevice was not attempted for the RusGuard ACM endpoint.")
            if not result.close_result.ok:
                raise OSError(self._format_operation_error("RG_CloseDevice", result.close_result.code))
            return _PONG_RESPONSE
        except RusGuardSdkError as error:
            raise OSError(f"RusGuard SDK ACM status check failed: {error}") from error
        finally:
            try:
                sdk.uninitialize()
            except RusGuardSdkError as error:
                raise OSError(f"RusGuard SDK ACM cleanup failed: {error}") from error

    def _select_target_endpoint(self, endpoint_infos: tuple[EndpointInfo, ...]) -> EndpointInfo:
        target = next((item for item in endpoint_infos if item.address == self.target_endpoint), None)
        if target is None:
            raise OSError(
                f"RusGuard ACM endpoint {self.target_endpoint} was not discovered via SDK SERIAL enumeration."
            )
        return target

    @staticmethod
    def _format_operation_error(operation: str, code: int) -> str:
        code_name, code_message = decode_api_error(code)
        return f"{operation} failed with code {code} ({code_name}: {code_message})"
