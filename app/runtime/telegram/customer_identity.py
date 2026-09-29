from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.customer_identity import CustomerIdentityService, SubmitCustomerIdentityCommand


@dataclass(frozen=True, slots=True)
class TelegramCustomerIdentityInput:
    telegram_user_id: int
    full_name: str
    shamcash_account: str
    telegram_contact_phone: str
    qr_image_file_id: str


@dataclass(frozen=True, slots=True)
class TelegramCustomerIdentityResponse:
    ok: bool
    message: str


class CustomerIdentityApplication(Protocol):
    async def submit(self, command: SubmitCustomerIdentityCommand): ...


class TelegramCustomerIdentityHandler:
    def __init__(self, service: CustomerIdentityApplication | CustomerIdentityService) -> None:
        self._service = service

    async def submit(
        self, data: TelegramCustomerIdentityInput
    ) -> TelegramCustomerIdentityResponse:
        try:
            await self._service.submit(
                SubmitCustomerIdentityCommand(
                    telegram_user_id=data.telegram_user_id,
                    full_name=data.full_name,
                    shamcash_account=data.shamcash_account,
                    telegram_contact_phone=data.telegram_contact_phone,
                    qr_image_file_id=data.qr_image_file_id,
                )
            )
        except ValueError:
            return TelegramCustomerIdentityResponse(False, "بيانات التحقق غير صالحة. تحقق منها وحاول مجددًا.")
        except Exception:
            return TelegramCustomerIdentityResponse(False, "تعذر إرسال طلب التحقق حاليًا. حاول لاحقًا.")
        return TelegramCustomerIdentityResponse(True, "تم إرسال بيانات التحقق للمراجعة.")