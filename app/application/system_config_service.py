from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from app.application.auth_service import AuthService
from app.application.dto.system_config import (
    ConfigValueDTO,
    EffectiveSystemConfigDTO,
    ExportConfigurationDTO,
    HardwareConfigurationDTO,
    HardwareEndpointConfigDTO,
    StartupConfigurationDTO,
    StorageConfigurationDTO,
    SystemConfigOverrideSnapshotDTO,
    SystemConfigPatchDTO,
)
from app.application.exceptions import AuthorizationError, ValidationError
from app.config import AppSettings, HardwareProvider
from app.domain.enums import RoleCode
from app.hardware.transport_config import HardwareEndpointTransportConfig
from app.persistence.models import AuditLog
from app.persistence.repositories.logs import AuditLogRepository
from app.persistence.repositories.service import SystemSettingRepository

_SETTING_KEY_HARDWARE_PROVIDER = "hardware.provider"
_SETTING_KEY_EXPORT_DEFAULT_DESTINATION_TYPE = "export.default_destination_type"
_SETTING_KEY_EXPORT_DEFAULT_DESTINATION_PATH = "export.default_destination_path"
_SUPPORTED_SETTING_KEYS = (
    _SETTING_KEY_EXPORT_DEFAULT_DESTINATION_PATH,
    _SETTING_KEY_EXPORT_DEFAULT_DESTINATION_TYPE,
    _SETTING_KEY_HARDWARE_PROVIDER,
)
_WRITABLE_FIELDS = (
    "hardware_provider",
    "export_default_destination_type",
    "export_default_destination_path",
)


@dataclass(slots=True)
class SystemConfigService:
    runtime_settings: AppSettings
    auth_service: AuthService
    system_setting_repository: SystemSettingRepository
    audit_log_repository: AuditLogRepository
    _default_hardware_provider: HardwareProvider | None = None
    _default_export_destination_type: str | None = None
    _default_export_destination_path: Path | None = None

    def __post_init__(self) -> None:
        self._default_hardware_provider = self.runtime_settings.hardware_provider
        self._default_export_destination_type = self.runtime_settings.export_default_destination_type
        self._default_export_destination_path = self.runtime_settings.export_default_destination_path

    def sync_runtime_settings(self) -> None:
        self._apply_runtime_overrides(self._load_persisted_override_values())

    def get_effective_config(self) -> EffectiveSystemConfigDTO:
        override_values = self._load_persisted_override_values()
        self._apply_runtime_overrides(override_values)
        return EffectiveSystemConfigDTO(
            hardware=HardwareConfigurationDTO(
                provider=ConfigValueDTO(
                    value=self.runtime_settings.hardware_provider.value,
                    source="override" if _SETTING_KEY_HARDWARE_PROVIDER in override_values else "default",
                    writable=True,
                ),
                real_endpoints=self._read_endpoint_configs(),
            ),
            startup=StartupConfigurationDTO(
                app_name=self.runtime_settings.app_name,
                app_environment=self.runtime_settings.app_environment,
                alembic_config_path=self._path_text(self.runtime_settings.alembic_config_path),
                startup_data_dir=self._path_text(self.runtime_settings.data_dir),
                startup_database_path=self._path_text(self.runtime_settings.sqlite_path),
            ),
            export=ExportConfigurationDTO(
                default_destination_type=ConfigValueDTO(
                    value=self.runtime_settings.export_default_destination_type,
                    source="override" if _SETTING_KEY_EXPORT_DEFAULT_DESTINATION_TYPE in override_values else "default",
                    writable=True,
                ),
                default_destination_path=ConfigValueDTO(
                    value=self._path_text(self.runtime_settings.export_default_destination_path),
                    source="override" if _SETTING_KEY_EXPORT_DEFAULT_DESTINATION_PATH in override_values else "default",
                    writable=True,
                ),
            ),
            storage=StorageConfigurationDTO(
                data_dir=self._path_text(self.runtime_settings.data_dir),
                sqlite_filename=self.runtime_settings.sqlite_filename,
                sqlite_path=self._path_text(self.runtime_settings.sqlite_path),
                database_url=self.runtime_settings.database_url,
            ),
            writable_fields=_WRITABLE_FIELDS,
        )

    def apply_overrides(self, patch: SystemConfigPatchDTO) -> EffectiveSystemConfigDTO:
        actor = self.auth_service.get_user_by_id(patch.actor_user_id)
        if actor.role_code not in {RoleCode.ADMIN, RoleCode.OPERATOR}:
            raise AuthorizationError(f"User role is not allowed for system config updates: {actor.role_code}")
        if not patch.provided_fields:
            raise ValidationError("At least one supported system config field is required")

        override_values = self._load_persisted_override_values()
        before_snapshot = self._effective_override_snapshot(override_values)

        if "hardware_provider" in patch.provided_fields:
            if patch.hardware_provider is None:
                self.system_setting_repository.delete_by_key(_SETTING_KEY_HARDWARE_PROVIDER)
                override_values.pop(_SETTING_KEY_HARDWARE_PROVIDER, None)
            else:
                override_values[_SETTING_KEY_HARDWARE_PROVIDER] = patch.hardware_provider.value
                self.system_setting_repository.upsert(
                    key=_SETTING_KEY_HARDWARE_PROVIDER,
                    value=json.dumps(patch.hardware_provider.value),
                    value_type="string",
                    description="Persisted hardware provider selection override.",
                )

        if "export_default_destination_type" in patch.provided_fields:
            if patch.export_default_destination_type is None:
                self.system_setting_repository.delete_by_key(_SETTING_KEY_EXPORT_DEFAULT_DESTINATION_TYPE)
                override_values.pop(_SETTING_KEY_EXPORT_DEFAULT_DESTINATION_TYPE, None)
            else:
                destination_type = self._validate_destination_type(patch.export_default_destination_type)
                override_values[_SETTING_KEY_EXPORT_DEFAULT_DESTINATION_TYPE] = destination_type
                self.system_setting_repository.upsert(
                    key=_SETTING_KEY_EXPORT_DEFAULT_DESTINATION_TYPE,
                    value=json.dumps(destination_type),
                    value_type="string",
                    description="Persisted default export destination type override.",
                )

        if "export_default_destination_path" in patch.provided_fields:
            if patch.export_default_destination_path is None:
                self.system_setting_repository.delete_by_key(_SETTING_KEY_EXPORT_DEFAULT_DESTINATION_PATH)
                override_values.pop(_SETTING_KEY_EXPORT_DEFAULT_DESTINATION_PATH, None)
            else:
                destination_path = self._validate_destination_path(patch.export_default_destination_path)
                override_values[_SETTING_KEY_EXPORT_DEFAULT_DESTINATION_PATH] = destination_path
                self.system_setting_repository.upsert(
                    key=_SETTING_KEY_EXPORT_DEFAULT_DESTINATION_PATH,
                    value=json.dumps(destination_path),
                    value_type="string",
                    description="Persisted default export destination path override.",
                )

        self._apply_runtime_overrides(override_values)
        after_snapshot = self._effective_override_snapshot(override_values)
        self.audit_log_repository.add(
            AuditLog(
                entity_type="system_config",
                entity_id="effective",
                action="system_config_update",
                actor_user_id=actor.user_id,
                reason_code=None,
                comment=patch.comment,
                before_json={
                    "hardware_provider": before_snapshot.hardware_provider,
                    "export_default_destination_type": before_snapshot.export_default_destination_type,
                    "export_default_destination_path": before_snapshot.export_default_destination_path,
                },
                after_json={
                    "hardware_provider": after_snapshot.hardware_provider,
                    "export_default_destination_type": after_snapshot.export_default_destination_type,
                    "export_default_destination_path": after_snapshot.export_default_destination_path,
                },
            )
        )
        self.system_setting_repository.session.commit()
        return self.get_effective_config()

    def _load_persisted_override_values(self) -> dict[str, str]:
        overrides: dict[str, str] = {}
        for row in self.system_setting_repository.list_by_keys(_SUPPORTED_SETTING_KEYS):
            try:
                raw_value = json.loads(row.value)
            except json.JSONDecodeError:
                continue
            if row.key == _SETTING_KEY_HARDWARE_PROVIDER:
                try:
                    overrides[row.key] = HardwareProvider(str(raw_value)).value
                except ValueError:
                    continue
            elif row.key == _SETTING_KEY_EXPORT_DEFAULT_DESTINATION_TYPE:
                try:
                    overrides[row.key] = self._validate_destination_type(str(raw_value))
                except ValidationError:
                    continue
            elif row.key == _SETTING_KEY_EXPORT_DEFAULT_DESTINATION_PATH:
                try:
                    overrides[row.key] = self._validate_destination_path(str(raw_value))
                except ValidationError:
                    continue
        return overrides

    def _apply_runtime_overrides(self, override_values: dict[str, str]) -> None:
        self.runtime_settings.hardware_provider = HardwareProvider(
            override_values.get(_SETTING_KEY_HARDWARE_PROVIDER, (self._default_hardware_provider or HardwareProvider.MOCK).value)
        )
        self.runtime_settings.export_default_destination_type = override_values.get(
            _SETTING_KEY_EXPORT_DEFAULT_DESTINATION_TYPE,
            self._default_export_destination_type or "filesystem",
        )
        export_path = override_values.get(
            _SETTING_KEY_EXPORT_DEFAULT_DESTINATION_PATH,
            str(self._default_export_destination_path or Path("var/exports")),
        )
        self.runtime_settings.export_default_destination_path = Path(export_path)

    def _read_endpoint_configs(self) -> tuple[HardwareEndpointConfigDTO, ...]:
        endpoints: list[HardwareEndpointConfigDTO] = []
        for endpoint_name in ("drum_controller", "lock_controller", "rfid_reader"):
            raw_config = self.runtime_settings.hardware_real_endpoints.get(endpoint_name)
            if raw_config is None:
                endpoints.append(
                    HardwareEndpointConfigDTO(
                        endpoint_name=endpoint_name,
                        configured=False,
                        config_status="not_configured",
                        driver_name=None,
                        endpoint_code=None,
                        transport=None,
                        location=None,
                        read_timeout_ms=None,
                        write_timeout_ms=None,
                        connect_timeout_ms=None,
                        config_error=None,
                    )
                )
                continue
            try:
                parsed = HardwareEndpointTransportConfig.model_validate(raw_config)
            except PydanticValidationError as error:
                endpoints.append(
                    HardwareEndpointConfigDTO(
                        endpoint_name=endpoint_name,
                        configured=True,
                        config_status="invalid",
                        driver_name=None,
                        endpoint_code=None,
                        transport=None,
                        location=None,
                        read_timeout_ms=None,
                        write_timeout_ms=None,
                        connect_timeout_ms=None,
                        config_error=error.errors()[0]["msg"],
                    )
                )
                continue
            endpoints.append(
                HardwareEndpointConfigDTO(
                    endpoint_name=endpoint_name,
                    configured=True,
                    config_status="valid",
                    driver_name=parsed.endpoint.driver_name,
                    endpoint_code=parsed.endpoint.code,
                    transport=parsed.transport.transport,
                    location=self._transport_location(parsed.transport),
                    read_timeout_ms=parsed.endpoint.timeouts.read_timeout_ms,
                    write_timeout_ms=parsed.endpoint.timeouts.write_timeout_ms,
                    connect_timeout_ms=parsed.endpoint.timeouts.connect_timeout_ms,
                    config_error=None,
                )
            )
        return tuple(endpoints)

    def _effective_override_snapshot(self, override_values: dict[str, str]) -> SystemConfigOverrideSnapshotDTO:
        hardware_provider = override_values.get(_SETTING_KEY_HARDWARE_PROVIDER, self.runtime_settings.hardware_provider.value)
        destination_type = override_values.get(
            _SETTING_KEY_EXPORT_DEFAULT_DESTINATION_TYPE,
            self.runtime_settings.export_default_destination_type,
        )
        destination_path = override_values.get(
            _SETTING_KEY_EXPORT_DEFAULT_DESTINATION_PATH,
            self._path_text(self.runtime_settings.export_default_destination_path),
        )
        return SystemConfigOverrideSnapshotDTO(
            hardware_provider=hardware_provider,
            export_default_destination_type=destination_type,
            export_default_destination_path=destination_path,
        )

    @staticmethod
    def _transport_location(transport: object) -> str | None:
        host = getattr(transport, "host", None)
        if host is not None:
            tcp_port = getattr(transport, "port", None)
            return f"{host}:{tcp_port}" if tcp_port is not None else str(host)
        port = getattr(transport, "port", None)
        if port is not None:
            return str(port)
        return None

    @staticmethod
    def _validate_destination_type(value: str) -> str:
        normalized = value.strip().lower()
        if normalized != "filesystem":
            raise ValidationError("export_default_destination_type must be 'filesystem'")
        return normalized

    @staticmethod
    def _validate_destination_path(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValidationError("export_default_destination_path must not be empty")
        invalid_chars = {char for char in normalized if ord(char) < 32}
        if invalid_chars:
            raise ValidationError("export_default_destination_path contains control characters")
        return normalized

    @staticmethod
    def _path_text(path: Path) -> str:
        return path.as_posix()
