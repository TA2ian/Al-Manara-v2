from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.application.submit_receipt import SubmitReceiptCommand


@dataclass(frozen=True, slots=True)
class TelegramReceiptInput:
    user_id: int
    order_id: UUID
    telegram_file_id: str
    mime_type: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class TelegramReceiptResponse:
    ok: bool
    text: str


class ReceiptMessages:
    INVALID = "بيانات الإيصال غير صالحة."
    ACCEPTED = "تم استلام الإيصال وإرساله للتحقق."
    FAILED = "تعذر التحقق من الإيصال. يرجى المحاولة بإيصال صالح."
    ERROR = "تعذر معالجة الإيصال حاليًا."


class ReceiptSubmissionService(Protocol):
    async def submit(self, command: SubmitReceiptCommand): ...


@dataclass(frozen=True, slots=True)
class TelegramReceiptHandler:
    """Framework-neutral Telegram adapter for receipt image submission."""

    submission: ReceiptSubmissionService

    async def submit(self, data: TelegramReceiptInput) -> TelegramReceiptResponse:
        if data.user_id <= 0:
            return TelegramReceiptResponse(False, ReceiptMessages.INVALID)
        if not isinstance(data.order_id, UUID):
            return TelegramReceiptResponse(False, ReceiptMessages.INVALID)
        if not data.telegram_file_id.strip() or not data.mime_type.strip() or not data.idempotency_key.strip():
            return TelegramReceiptResponse(False, ReceiptMessages.INVALID)

        try:
            await self.submission.submit(
                SubmitReceiptCommand(
                    order_id=data.order_id,
                    telegram_user_id=data.user_id,
                    telegram_file_id=data.telegram_file_id,
                    mime_type=data.mime_type,
                    idempotency_key=data.idempotency_key,
                )
            )
        except ValueError:
            return TelegramReceiptResponse(False, ReceiptMessages.FAILED)
        except Exception:
            return TelegramReceiptResponse(False, ReceiptMessages.ERROR)
        return TelegramReceiptResponse(True, ReceiptMessages.ACCEPTED)
