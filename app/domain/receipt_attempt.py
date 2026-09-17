from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ReceiptInputType(StrEnum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"


class ReceiptAttemptStatus(StrEnum):
    PROCESSING = "processing"
    FAILED = "failed"
    VERIFIED = "verified"
    ESCALATED = "escalated"


SUPPORTED_RECEIPT_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_RECEIPT_ATTEMPTS = 3
MAX_TRANSACTION_REFERENCE_LENGTH = 128


@dataclass(frozen=True, slots=True)
class ReceiptAttempt:
    attempt_id: UUID
    order_id: UUID
    attempt_number: int
    input_type: ReceiptInputType
    transaction_reference: str | None
    mime_type: str | None
    telegram_file_id: str | None
    submitted_at: datetime
    status: ReceiptAttemptStatus
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.attempt_number <= MAX_RECEIPT_ATTEMPTS:
            raise ValueError("receipt attempt number must be between 1 and 3")
        if self.submitted_at.tzinfo is None:
            raise ValueError("submitted_at must be timezone-aware")

        reference = self.transaction_reference.strip() if self.transaction_reference is not None else None
        file_id = self.telegram_file_id.strip() if self.telegram_file_id is not None else None
        mime = self.mime_type.strip().lower() if self.mime_type is not None else None

        if self.input_type is ReceiptInputType.TEXT:
            if not reference or len(reference) > MAX_TRANSACTION_REFERENCE_LENGTH:
                raise ValueError("text receipt requires a valid transaction reference")
            if any(ord(char) < 32 or ord(char) == 127 for char in reference):
                raise ValueError("transaction reference contains control characters")
            if file_id is not None or mime is not None:
                raise ValueError("text receipt cannot contain image fields")
        elif self.input_type is ReceiptInputType.IMAGE:
            if mime not in SUPPORTED_RECEIPT_MIME_TYPES:
                raise ValueError("unsupported receipt MIME type")
            if not file_id:
                raise ValueError("image receipt requires a Telegram file id")
            if reference is not None:
                raise ValueError("image receipt cannot contain a transaction reference")
        else:
            raise ValueError("unsupported receipt input type")

        if self.status in (ReceiptAttemptStatus.FAILED, ReceiptAttemptStatus.ESCALATED):
            if not (self.failure_reason or "").strip():
                raise ValueError("failed or escalated receipt attempts require a failure reason")
        elif self.failure_reason is not None:
            raise ValueError("failure reason is only valid for failed or escalated attempts")
