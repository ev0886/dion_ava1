from __future__ import annotations

from datetime import date
from pathlib import Path

from app.application.admin_service import AdminOperationService
from app.application.dto.usb_storage import UsbOperationsExportResultDTO
from app.application.exceptions import ValidationError
from app.application.usb_storage_service import UsbStorageDiscoveryService


class LocalUsbExportService:
    def __init__(
        self,
        *,
        usb_storage: UsbStorageDiscoveryService,
        admin_operations: AdminOperationService,
    ) -> None:
        self._usb_storage = usb_storage
        self._admin_operations = admin_operations

    def export_operations_csv(self, *, date_from: date, date_to: date) -> UsbOperationsExportResultDTO:
        if date_from > date_to:
            raise ValidationError("date_from must be less than or equal to date_to")

        usb_status = self._usb_storage.get_status()
        if not usb_status.usb_available or not usb_status.mount_path:
            raise ValidationError(
                "USB-\u043d\u043e\u0441\u0438\u0442\u0435\u043b\u044c \u043d\u0435 \u043e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d. "
                "\u042d\u043a\u0441\u043f\u043e\u0440\u0442 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d."
            )
        if not usb_status.writable:
            raise ValidationError(
                "USB-\u043d\u043e\u0441\u0438\u0442\u0435\u043b\u044c \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d "
                "\u0434\u043b\u044f \u0437\u0430\u043f\u0438\u0441\u0438."
            )

        mount_path = Path(usb_status.mount_path)
        if not mount_path.exists() or not mount_path.is_dir():
            raise ValidationError(
                "\u0422\u043e\u0447\u043a\u0430 \u043c\u043e\u043d\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f USB "
                "\u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430."
            )

        csv_text = self._admin_operations.export_operations_csv(date_from=date_from, date_to=date_to)
        file_name = f"dion-operations-{date_from.strftime('%Y%m%d')}-{date_to.strftime('%Y%m%d')}.csv"
        target_path = mount_path / file_name

        try:
            target_path.write_text(csv_text, encoding="utf-8-sig")
        except OSError as exc:
            raise ValidationError(
                f"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u043f\u0438\u0441\u0430\u0442\u044c CSV \u043d\u0430 USB: {exc}"
            ) from exc

        return UsbOperationsExportResultDTO(
            success=True,
            file_path=str(target_path),
            file_name=file_name,
            mount_path=str(mount_path),
        )
