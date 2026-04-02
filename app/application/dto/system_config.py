from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.config import HardwareProvider


ConfigSource = Literal["default", "override"]


@dataclass(frozen=True, slots=True)
class ConfigValueDTO:
    value: object
    source: ConfigSource
    writable: bool


@dataclass(frozen=True, slots=True)
class HardwareEndpointConfigDTO:
    endpoint_name: str
    configured: bool
    config_status: Literal["valid", "invalid", "not_configured"]
    driver_name: str | None
    endpoint_code: str | None
    transport: str | None
    location: str | None
    read_timeout_ms: int | None
    write_timeout_ms: int | None
    connect_timeout_ms: int | None
    config_error: str | None


@dataclass(frozen=True, slots=True)
class HardwareConfigurationDTO:
    provider: ConfigValueDTO
    real_endpoints: tuple[HardwareEndpointConfigDTO, ...]


@dataclass(frozen=True, slots=True)
class StartupConfigurationDTO:
    app_name: str
    app_environment: str
    alembic_config_path: str
    startup_data_dir: str
    startup_database_path: str


@dataclass(frozen=True, slots=True)
class ExportConfigurationDTO:
    default_destination_type: ConfigValueDTO
    default_destination_path: ConfigValueDTO


@dataclass(frozen=True, slots=True)
class StorageConfigurationDTO:
    data_dir: str
    sqlite_filename: str
    sqlite_path: str
    database_url: str


@dataclass(frozen=True, slots=True)
class EffectiveSystemConfigDTO:
    hardware: HardwareConfigurationDTO
    startup: StartupConfigurationDTO
    export: ExportConfigurationDTO
    storage: StorageConfigurationDTO
    writable_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SystemConfigPatchDTO:
    actor_user_id: int
    provided_fields: frozenset[str]
    hardware_provider: HardwareProvider | None = None
    export_default_destination_type: str | None = None
    export_default_destination_path: str | None = None
    comment: str | None = None


@dataclass(frozen=True, slots=True)
class SystemConfigOverrideSnapshotDTO:
    hardware_provider: str
    export_default_destination_type: str
    export_default_destination_path: str
