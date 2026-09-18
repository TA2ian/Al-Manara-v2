from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.application.receipt_image import ReceiptImageInspectorImpl
from app.application.receipt_ports import ReceiptAttemptRepository, ReceiptClock
from app.domain.receipt_attempt import ReceiptAttempt, ReceiptAttemptStatus, ReceiptInputType, SUPPORTED_RECEIPT_MIME_TYPES


@dataclass(frozen=True, slots=True)
class SubmitCustomerReceiptCommand:
    order_id: UUID
    telegram_user_id: int
    telegram_file_id: str
    declared_mime_type: str
    idempotency_key: str


class SubmitCustomerReceiptService:
    """Validates a Telegram image, reserves it, then queues it for human review.

    This boundary deliberately does not perform financial approval or infer payment
    validity. The database moves the order to UNDER_REVIEW only after the image has
    passed strict content validation and the receipt attempt has been reserved.
    """

    def __init__(
        self,
        attempts: ReceiptAttemptRepository,
        inspector: ReceiptImageInspectorImpl,
        clock: ReceiptClock,
    ) -> None:
        self._attempts = attempts
        self._inspector = inspector
        self._clock = clock

    async def submit(self, command: SubmitCustomerReceiptCommand, image_bytes: bytes) -> ReceiptAttempt:
        if not isinstance(command.order_id, UUID):
            raise ValueError("order id is required")
        if not isinstance(command.telegram_user_id, int) or command.telegram_user_id <= 0:
            raise ValueError("telegram user id must be positive")
        file_id = command.telegram_file_id.strip()
        if not file_id:
            raise ValueError("telegram file id is required")
        mime = command.declared_mime_type.strip().lower()
        if mime not in SUPPORTED_RECEIPT_MIME_TYPES:
            raise ValueError("unsupported receipt image type")
        key = command.idempotency_key.strip()
        if not key:
            raise ValueError("idempotency key is required")
        submitted_at = self._clock.now()
        if submitted_at.tzinfo is None:
            raise RuntimeError("receipt clock must return a timezone-aware datetime")

        inspected = await self._inspector.inspect_bytes(image_bytes, mime)
        reservation = await self._attempts.reserve_next_attempt(
            order_id=command.order_id,
            telegram_user_id=command.telegram_user_id,
            idempotency_key=key,
            submitted_at=submitted_at,
            input_type=ReceiptInputType.IMAGE,
            transaction_reference=None,
            mime_type=inspected.mime_type,
            telegram_file_id=file_id,
        )
        if reservation.replayed:
            return reservation.attempt
        return await self._attempts.finalize(
            reservation.attempt.attempt_id,
            ReceiptAttemptStatus.SUBMITTED,
        )
