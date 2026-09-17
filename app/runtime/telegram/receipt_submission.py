from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.application.submit_receipt import SubmitReceiptCommand
from app.domain.receipt_attempt import ReceiptInputType, SUPPORTED_RECEIPT_MIME_TYPES


@dataclass(frozen=True, slots=True)
class TelegramReceiptInput:
    user_id: int
    order_id: UUID
    input_type: ReceiptInputType
    idempotency_key: str
    transaction_reference: str | None = None
    telegram_file_id: str | None = None
    mime_type: str | None = None


@dataclass(frozen=True, slots=True)
class TelegramReceiptResponse:
    ok: bool
    text: str


class ReceiptMessages:
    INVALID = "بيانات الإيصال غير صالحة."
    PDF_GUIDANCE = "يرجى إرسال صورة الإيصال (JPG أو PNG أو WEBP) بدل ملف PDF."
    UNSUPPORTED_FORMAT = "يرجى إرسال صورة الإيصال بصيغة JPG أو PNG أو WEBP."
    ACCEPTED = "تم استلام صورة الإيصال وإرسالها للتحقق."
    FAILED = "تعذر التحقق من الإيصال. يرجى إرسال صورة واضحة وصالحة."
    ERROR = "تعذر معالجة الإيصال حاليًا."


class ReceiptSubmissionService(Protocol):
    async def submit(self, command: SubmitReceiptCommand): ...


@dataclass(frozen=True, slots=True)
class TelegramReceiptHandler:
    """Telegram adapter for image-only customer receipt submission."""

    submission: ReceiptSubmissionService

    async def submit(self, data: TelegramReceiptInput) -> TelegramReceiptResponse:
        if data.user_id <= 0:
            return TelegramReceiptResponse(False, ReceiptMessages.INVALID)
        if not isinstance(data.order_id, UUID):
            return TelegramReceiptResponse(False, ReceiptMessages.INVALID)
        if data.input_type is not ReceiptInputType.IMAGE:
            return TelegramReceiptResponse(False, ReceiptMessages.UNSUPPORTED_FORMAT)
        if not data.idempotency_key.strip():
            return TelegramReceiptResponse(False, ReceiptMessages.INVALID)

        telegram_file_id = data.telegram_file_id.strip() if data.telegram_file_id is not None else None
        mime_type = data.mime_type.strip().lower() if data.mime_type is not None else None

        if not telegram_file_id or mime_type not in SUPPORTED_RECEIPT_MIME_TYPES:
            return TelegramReceiptResponse(False, ReceiptMessages.UNSUPPORTED_FORMAT)
        if data.transaction_reference is not None:
            return TelegramReceiptResponse(False, ReceiptMessages.INVALID)

        try:
            await self.submission.submit(
                SubmitReceiptCommand(
                    order_id=data.order_id,
                    telegram_user_id=data.user_id,
                    input_type=ReceiptInputType.IMAGE,
                    transaction_reference=None,
                    telegram_file_id=telegram_file_id,
                    mime_type=mime_type,
                    idempotency_key=data.idempotency_key.strip(),
                )
            )
        except ValueError:
            return TelegramReceiptResponse(False, ReceiptMessages.FAILED)
        except Exception:
            return TelegramReceiptResponse(False, ReceiptMessages.ERROR)
        return TelegramReceiptResponse(True, ReceiptMessages.ACCEPTED)
