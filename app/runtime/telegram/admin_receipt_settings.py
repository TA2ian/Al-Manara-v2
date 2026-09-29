from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.admin_receipt_settings import AdminReceiptSettingsService, ReceiptWindowSetting


@dataclass(frozen=True, slots=True)
class TelegramAdminReceiptSettingsResponse:
    ok: bool
    setting: ReceiptWindowSetting | None = None
    confirmation_id: UUID | None = None
    message: str = ""


class TelegramAdminReceiptSettingsHandler:
    def __init__(self, service: AdminReceiptSettingsService) -> None:
        self._service = service

    async def get(self) -> TelegramAdminReceiptSettingsResponse:
        try:
            setting = await self._service.get()
        except Exception:
            return TelegramAdminReceiptSettingsResponse(False, message="تعذر تحميل مهلة الإيصال.")
        return TelegramAdminReceiptSettingsResponse(True, setting=setting, message="تم تحميل الإعداد.")

    async def request_update(self, admin_user_id: int, actor_type: str, session_id: UUID, minutes: int) -> TelegramAdminReceiptSettingsResponse:
        try:
            confirmation_id = await self._service.request_update(admin_user_id, actor_type, session_id, minutes)
        except (ValueError, PermissionError):
            return TelegramAdminReceiptSettingsResponse(False, message="قيمة المهلة أو صلاحيات المدير غير صالحة.")
        except Exception:
            return TelegramAdminReceiptSettingsResponse(False, message="تعذر تجهيز تأكيد تغيير مهلة الإيصال.")
        return TelegramAdminReceiptSettingsResponse(True, confirmation_id=confirmation_id, message="التغيير جاهز للتأكيد.")

    async def confirm_update(self, admin_user_id: int, actor_type: str, confirmation_id: UUID, minutes: int) -> TelegramAdminReceiptSettingsResponse:
        try:
            setting = await self._service.confirm_update(admin_user_id, actor_type, confirmation_id, minutes)
        except (ValueError, PermissionError):
            return TelegramAdminReceiptSettingsResponse(False, message="التأكيد أو صلاحيات المدير غير صالحة.")
        except Exception:
            return TelegramAdminReceiptSettingsResponse(False, message="تعذر حفظ مهلة الإيصال.")
        return TelegramAdminReceiptSettingsResponse(True, setting=setting, message="تم تحديث مهلة إرسال الإيصال.")
