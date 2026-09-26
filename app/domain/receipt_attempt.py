from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ReceiptInputType(StrEnum):
    # TEXT remains readable for legacy persisted records, but new submissions are image-only.
    TEXT = "TEXT"
    IMAGE = "IMAGE"


class ReceiptAttemptStatus(StrEnum):
    PROCESSING = "processing"
    SUBMITTED = "submitted"
    FAILED = "failed"
    VERIFIED = "verified"
    ESCALATED = "escalated"


SUPPORTED_RECEIPT_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_RECEIPT_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class ReceiptAttempt:
    attempt_id: UUID
    order_id: UUID
    attempt_number: int
    mime_type: str | None
    telegram_file_id: str | None
    submitted_at: datetime
    status: ReceiptAttemptStatus
    input_type: ReceiptInputType = ReceiptInputType.IMAGE
    transaction_reference: str | None = None
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.attempt_number <= MAX_RECEIPT_ATTEMPTS:
            raise ValueError("receipt attempt number must be between 1 and 3")
        if self.submitted_at.tzinfo is None:
            raise ValueError("submitted_at must be timezone-aware")

        reference = self.transaction_reference.strip() if self.transaction_reference is not None else None
        file_id = self.telegram_file_id.strip() if self.telegram_file_id is not None else None
        mime = self.mime_type.strip().lower() if self.mime_type is not None else None

        # Customer receipt submissions are intentionally image-only.
        # TEXT is retained only so legacy persisted rows can still be represented.
        if self.input_type is ReceiptInputType.TEXT:
            raise ValueError("text receipt submission is not supported")
        if self.input_type is not ReceiptInputType.IMAGE:
            raise ValueError("unsupported receipt input type")
        if mime not in SUPPORTED_RECEIPT_MIME_TYPES:
            raise ValueError("unsupported receipt MIME type")
        if not file_id:
            raise ValueError("image receipt requires a Telegram file id")
        if reference is not None:
            raise ValueError("image receipt cannot contain a transaction reference")

        if self.status in (ReceiptAttemptStatus.FAILED, ReceiptAttemptStatus.ESCALATED):
            if not (self.failure_reason or "").strip():
                raise ValueError("failed or escalated receipt attempts require a failure reason")
        elif self.failure_reason is not None:
            raise ValueError("failure reason is only valid for failed or escalated attempts")
