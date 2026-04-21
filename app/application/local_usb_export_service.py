from __future__ import annotations

import csv
from datetime import date, datetime
from io import StringIO
from pathlib import Path

from app.application.admin_service import AdminOperationService, AdminUserService
from app.application.dto.usb_storage import (
    UsbBalancesExportResultDTO,
    UsbOperationsExportResultDTO,
    UsbUsersExportResultDTO,
    UsbUsersImportCheckResultDTO,
    UsbUsersImportResultDTO,
)
from app.application.exceptions import ValidationError
from app.application.usb_storage_service import UsbStorageDiscoveryService
from app.persistence.models import AuditLog, EventLog
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository


class LocalUsbExportService:
    _USERS_IMPORT_FILE_NAME = "users_import.csv"
    _USB_MISSING_MESSAGE = "USB-носитель не найден"
    _USB_DAMAGED_MESSAGE = "USB-носитель поврежден"

    def __init__(
        self,
        *,
        usb_storage: UsbStorageDiscoveryService,
        admin_operations: AdminOperationService,
        admin_users: AdminUserService,
        inventory_repository: InventoryRepository | None = None,
        event_log_repository: EventLogRepository | None = None,
        audit_log_repository: AuditLogRepository | None = None,
    ) -> None:
        self._usb_storage = usb_storage
        self._admin_operations = admin_operations
        self._admin_users = admin_users
        session = self._admin_users.user_repository.session
        self._inventory_repository = inventory_repository or InventoryRepository(session)
        self._event_log_repository = event_log_repository or EventLogRepository(session)
        self._audit_log_repository = audit_log_repository or AuditLogRepository(session)

    def export_operations_csv(self, *, date_from: date, date_to: date) -> UsbOperationsExportResultDTO:
        file_name = (
            f"operations_{date_from.strftime('%d-%m-%Y')}_{date_to.strftime('%d-%m-%Y')}"
            f"_{self._timestamp_now().strftime('%H-%M-%S')}.csv"
        )
        try:
            mount_path = self._resolve_mount_path(require_writable=True)
            csv_text = self._admin_operations.export_operations_csv_for_admin_touch(
                date_from=date_from,
                date_to=date_to,
            )
            target_path = self._write_csv_to_mount_root(mount_path=mount_path, file_name=file_name, csv_text=csv_text)
            self._record_success(action="export_operations", file_name=file_name, mount_path=mount_path)
            return UsbOperationsExportResultDTO(
                success=True,
                file_path=str(target_path),
                file_name=file_name,
                mount_path=str(mount_path),
            )
        except Exception as exc:
            self._record_failure(action="export_operations", message=str(exc), file_name=file_name)
            raise

    def export_users_csv(self) -> UsbUsersExportResultDTO:
        file_name = f"users_export_{self._timestamp_now().strftime('%d-%m-%Y_%H-%M-%S')}.csv"
        try:
            mount_path = self._resolve_mount_path(require_writable=True)
            csv_text = self._admin_users.export_users_csv()
            target_path = self._write_csv_to_mount_root(mount_path=mount_path, file_name=file_name, csv_text=csv_text)
            self._record_success(action="export_users", file_name=file_name, mount_path=mount_path)
            return UsbUsersExportResultDTO(
                success=True,
                file_path=str(target_path),
                file_name=file_name,
                mount_path=str(mount_path),
            )
        except Exception as exc:
            self._record_failure(action="export_users", message=str(exc), file_name=file_name)
            raise

    def export_balances_csv(self) -> UsbBalancesExportResultDTO:
        file_name = f"balances_export_{self._timestamp_now().strftime('%d-%m-%Y_%H-%M-%S')}.csv"
        try:
            mount_path = self._resolve_mount_path(require_writable=True)
            csv_text = self._build_balances_csv()
            target_path = self._write_csv_to_mount_root(mount_path=mount_path, file_name=file_name, csv_text=csv_text)
            self._record_success(action="export_balances", file_name=file_name, mount_path=mount_path)
            return UsbBalancesExportResultDTO(
                success=True,
                file_path=str(target_path),
                file_name=file_name,
                mount_path=str(mount_path),
            )
        except Exception as exc:
            self._record_failure(action="export_balances", message=str(exc), file_name=file_name)
            raise

    def check_users_import_csv(self) -> UsbUsersImportCheckResultDTO:
        mount_path = self._resolve_mount_path(require_readable=True)
        source_path = mount_path / self._USERS_IMPORT_FILE_NAME
        if not source_path.exists() or not source_path.is_file():
            raise ValidationError("Файл users_import.csv не найден")
        return UsbUsersImportCheckResultDTO(
            success=True,
            file_path=str(source_path),
            file_name=self._USERS_IMPORT_FILE_NAME,
            mount_path=str(mount_path),
        )

    def import_users_csv(self) -> UsbUsersImportResultDTO:
        try:
            check_result = self.check_users_import_csv()
            csv_text = self._read_csv_from_mount_root(source_path=Path(check_result.file_path))
            result = self._admin_users.import_new_users_csv(csv_text)
            self._record_success(
                action="import_users",
                file_name=check_result.file_name,
                mount_path=Path(check_result.mount_path),
            )
            return UsbUsersImportResultDTO(
                success=True,
                file_path=check_result.file_path,
                file_name=check_result.file_name,
                mount_path=check_result.mount_path,
                created_count=result.created_count,
                updated_count=result.updated_count,
                total_rows=result.total_rows,
            )
        except Exception as exc:
            self._record_failure(action="import_users", message=str(exc), file_name=self._USERS_IMPORT_FILE_NAME)
            raise

    def _resolve_mount_path(self, *, require_readable: bool = False, require_writable: bool = False) -> Path:
        usb_status = self._usb_storage.get_status()
        if not usb_status.usb_available or not usb_status.mount_path:
            raise ValidationError(self._USB_MISSING_MESSAGE)

        if require_readable and not usb_status.readable:
            raise ValidationError(self._USB_DAMAGED_MESSAGE)
        if require_writable and not usb_status.writable:
            raise ValidationError(self._USB_DAMAGED_MESSAGE)

        mount_path = Path(usb_status.mount_path)
        if not mount_path.exists() or not mount_path.is_dir():
            raise ValidationError(self._USB_DAMAGED_MESSAGE)
        return mount_path

    def _build_balances_csv(self) -> str:
        output = StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(("Номенклатура", "Количество"))
        for row in self._inventory_repository.list_filled_balance_summaries():
            writer.writerow((row.item_name, row.quantity))
        return output.getvalue()

    def _record_success(self, *, action: str, file_name: str, mount_path: Path) -> None:
        self._record_event_and_audit(
            action=action,
            result="success",
            message=file_name,
            payload={
                "file_name": file_name,
                "mount_path": str(mount_path),
            },
        )

    def _record_failure(self, *, action: str, message: str, file_name: str | None = None) -> None:
        self._record_event_and_audit(
            action=action,
            result="failed",
            message=message,
            payload={"file_name": file_name} if file_name else None,
        )

    def _record_event_and_audit(
        self,
        *,
        action: str,
        result: str,
        message: str,
        payload: dict[str, object] | None,
    ) -> None:
        self._event_log_repository.add(
            EventLog(
                event_type=action,
                level="info" if result == "success" else "error",
                source="admin_touch_usb",
                operation_id=None,
                session_id=None,
                user_id=None,
                slot_id=None,
                item_id=None,
                qty=None,
                result=result,
                comment=message,
                message=message,
                payload_json=dict(payload or {}),
            )
        )
        self._audit_log_repository.add(
            AuditLog(
                entity_type="admin_touch_usb",
                entity_id=action,
                action=action,
                actor_user_id=None,
                reason_code=result,
                comment=message,
                before_json=None,
                after_json=dict(payload or {}),
            )
        )
        self._event_log_repository.session.commit()

    @classmethod
    def _write_csv_to_mount_root(cls, *, mount_path: Path, file_name: str, csv_text: str) -> Path:
        target_path = mount_path / file_name
        try:
            target_path.write_text(csv_text, encoding="utf-8-sig")
        except OSError as exc:
            raise ValidationError(cls._USB_DAMAGED_MESSAGE) from exc
        return target_path

    @classmethod
    def _read_csv_from_mount_root(cls, *, source_path: Path) -> str:
        try:
            return source_path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise ValidationError(cls._USB_DAMAGED_MESSAGE) from exc

    @staticmethod
    def _timestamp_now() -> datetime:
        return datetime.now()
