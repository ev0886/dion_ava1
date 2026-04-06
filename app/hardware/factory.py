from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from app.config import AppSettings, HardwareProvider
from app.hardware.contracts import DrumControllerContract, LockControllerContract, RfidReaderContract
from app.hardware.drum_mock import MockDrumAdapter
from app.hardware.drum_real import RealDrumAdapter
from app.hardware.drum_stub_real import StubRealDrumAdapter
from app.hardware.dto import LockState
from app.hardware.facade import HardwareFacade
from app.hardware.lock_mock import MockLockAdapter
from app.hardware.lock_real import RealLockAdapter
from app.hardware.lock_stub_real import StubRealLockAdapter
from app.hardware.rfid_mock import MockRfidAdapter
from app.hardware.rfid_real import RealRfidAdapter
from app.hardware.rfid_stub_real import StubRealRfidAdapter
from app.hardware.transport_config import (
    HardwareEndpointTransportConfig,
    REAL_HARDWARE_ENDPOINT_NAMES,
    real_hardware_endpoints_example_json,
)
from app.hardware.transports import (
    SerialRequestResponseTransport,
    SerialTransport,
    TcpRequestResponseTransport,
    TcpTransport,
)


@dataclass(frozen=True, slots=True)
class HardwareBundle:
    provider: HardwareProvider
    drum_controller: DrumControllerContract
    lock_controller: LockControllerContract
    rfid_reader: RfidReaderContract
    facade: HardwareFacade


@dataclass(frozen=True, slots=True)
class ParsedEndpointConfig:
    config: HardwareEndpointTransportConfig | None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class RealEndpointConfigSummaryEntry:
    endpoint_name: str
    configured: bool
    enabled: bool | None
    transport: str | None
    target: str | None
    code: str | None
    driver_name: str | None
    validation_error: str | None = None


@dataclass(frozen=True, slots=True)
class RealEndpointConfigSummary:
    entries: tuple[RealEndpointConfigSummaryEntry, ...]
    warnings: tuple[str, ...]


def create_hardware_bundle(
    settings: AppSettings,
    *,
    transport_overrides: dict[str, SerialRequestResponseTransport | TcpRequestResponseTransport] | None = None,
) -> HardwareBundle:
    """Create the configured hardware bundle without changing provider-selection semantics."""

    provider = settings.hardware_provider
    if provider is HardwareProvider.STUB_REAL:
        return _build_stub_real_hardware(provider)
    if provider is HardwareProvider.REAL:
        return _build_real_hardware(settings, provider, transport_overrides=transport_overrides or {})
    return _build_mock_hardware(provider)


def _build_mock_hardware(provider: HardwareProvider) -> HardwareBundle:
    drum_controller = MockDrumAdapter()
    lock_controller = MockLockAdapter(lock_states={(1, 1): LockState.LOCKED})
    rfid_reader = MockRfidAdapter()
    return _bundle_from_parts(provider, drum_controller=drum_controller, lock_controller=lock_controller, rfid_reader=rfid_reader)


def _build_stub_real_hardware(provider: HardwareProvider) -> HardwareBundle:
    drum_controller = StubRealDrumAdapter()
    lock_controller = StubRealLockAdapter()
    rfid_reader = StubRealRfidAdapter()
    return _bundle_from_parts(provider, drum_controller=drum_controller, lock_controller=lock_controller, rfid_reader=rfid_reader)


def _build_real_hardware(
    settings: AppSettings,
    provider: HardwareProvider,
    *,
    transport_overrides: dict[str, SerialRequestResponseTransport | TcpRequestResponseTransport],
) -> HardwareBundle:
    """Build real adapters so each endpoint can fail independently and degrade readiness safely."""

    raw_configs = settings.hardware_real_endpoints
    drum_config = _parse_endpoint_config(raw_configs.get("drum_controller"), endpoint_name="drum_controller")
    lock_config = _parse_endpoint_config(raw_configs.get("lock_controller"), endpoint_name="lock_controller")
    rfid_config = _parse_endpoint_config(raw_configs.get("rfid_reader"), endpoint_name="rfid_reader")

    drum_controller = RealDrumAdapter(
        config=drum_config.config,
        transport=transport_overrides.get("drum_controller") or _create_transport_client(drum_config.config),
        config_error=drum_config.error_message,
    )
    lock_controller = RealLockAdapter(
        config=lock_config.config,
        transport=transport_overrides.get("lock_controller") or _create_transport_client(lock_config.config),
        config_error=lock_config.error_message,
    )
    rfid_reader = RealRfidAdapter(
        config=rfid_config.config,
        transport=transport_overrides.get("rfid_reader") or _create_transport_client(rfid_config.config),
        config_error=rfid_config.error_message,
    )
    return _bundle_from_parts(provider, drum_controller=drum_controller, lock_controller=lock_controller, rfid_reader=rfid_reader)


def _bundle_from_parts(
    provider: HardwareProvider,
    *,
    drum_controller: DrumControllerContract,
    lock_controller: LockControllerContract,
    rfid_reader: RfidReaderContract,
) -> HardwareBundle:
    return HardwareBundle(
        provider=provider,
        drum_controller=drum_controller,
        lock_controller=lock_controller,
        rfid_reader=rfid_reader,
        facade=HardwareFacade(
            drum_controller=drum_controller,
            lock_controller=lock_controller,
            rfid_reader=rfid_reader,
        ),
    )


def _parse_endpoint_config(raw_config: object, *, endpoint_name: str) -> ParsedEndpointConfig:
    if raw_config is None:
        return ParsedEndpointConfig(config=None, error_message=None)
    try:
        return ParsedEndpointConfig(config=HardwareEndpointTransportConfig.model_validate(raw_config))
    except ValidationError as error:
        first_error = error.errors()[0]
        location = ".".join(str(part) for part in first_error.get("loc", ()))
        detail = first_error["msg"]
        if location:
            detail = f"{location}: {detail}"
        return ParsedEndpointConfig(
            config=None,
            error_message=(
                f"{endpoint_name} real transport config is invalid: {detail}. "
                f"Expected inside DION_HARDWARE_REAL_ENDPOINTS. Example JSON: {real_hardware_endpoints_example_json()}"
            ),
        )


def summarize_real_endpoint_configs(settings: AppSettings) -> RealEndpointConfigSummary:
    raw_configs = settings.hardware_real_endpoints
    warnings = _collect_real_endpoint_warnings(raw_configs)
    entries = tuple(
        _summarize_real_endpoint_config(endpoint_name, raw_configs.get(endpoint_name))
        for endpoint_name in REAL_HARDWARE_ENDPOINT_NAMES
    )
    return RealEndpointConfigSummary(entries=entries, warnings=warnings)


def _collect_real_endpoint_warnings(raw_configs: dict[str, object]) -> tuple[str, ...]:
    unexpected_keys = sorted(set(raw_configs) - set(REAL_HARDWARE_ENDPOINT_NAMES))
    if not unexpected_keys:
        return ()
    expected = ", ".join(REAL_HARDWARE_ENDPOINT_NAMES)
    return (
        f"Unexpected real endpoint keys: {', '.join(unexpected_keys)}. Expected keys: {expected}.",
    )


def _summarize_real_endpoint_config(endpoint_name: str, raw_config: object) -> RealEndpointConfigSummaryEntry:
    parsed = _parse_endpoint_config(raw_config, endpoint_name=endpoint_name)
    if parsed.config is None:
        return RealEndpointConfigSummaryEntry(
            endpoint_name=endpoint_name,
            configured=raw_config is not None,
            enabled=None,
            transport=None,
            target=None,
            code=None,
            driver_name=None,
            validation_error=parsed.error_message,
        )

    transport = parsed.config.transport.transport
    target = (
        parsed.config.transport.port
        if transport == "serial"
        else f"{parsed.config.transport.host}:{parsed.config.transport.port}"
    )
    return RealEndpointConfigSummaryEntry(
        endpoint_name=endpoint_name,
        configured=True,
        enabled=parsed.config.endpoint.enabled,
        transport=transport,
        target=target,
        code=parsed.config.endpoint.code,
        driver_name=parsed.config.endpoint.driver_name,
        validation_error=None,
    )


def _create_transport_client(
    config: HardwareEndpointTransportConfig | None,
) -> SerialRequestResponseTransport | TcpRequestResponseTransport | None:
    if config is None:
        return None
    if config.transport.transport == "serial":
        return SerialTransport(settings=config.transport, timeouts=config.endpoint.timeouts)
    return TcpTransport(settings=config.transport, timeouts=config.endpoint.timeouts)
