from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.receipt_ports import (
    ReceiptAttemptRepository,
    ReceiptClock,
    ReceiptEscalationPort,
    ReceiptImageInspector,
    ReceiptVerifier,
)
from app.domain.receipt_attempt import (
    ReceiptAttempt,
    ReceiptAttemptStatus,
    ReceiptInputType,
    SUPPORTED_RECEIPT_MIME_TYPES,
    MAX_TRANSACTION_REFERENCE_LENGTH,
)


@dataclass(frozen=True, slots=True)
class SubmitReceiptCommand:
    order_id: UUID
    telegram_user_id: int
    input_type: ReceiptInputType
    transaction_reference: str | None
    telegram_file_id: str | None
    mime_type: str | None
    idempotency_key: str


class SubmitReceiptService:
    def __init__(
        self,
        attempts: ReceiptAttemptRepository,
        inspector: ReceiptImageInspector,
        verifier: ReceiptVerifier,
        escalation: ReceiptEscalationPort,
        clock: ReceiptClock,
    ) -> None:
        self._attempts = attempts
        self._inspector = inspector
        self._verifier = verifier
        self._escalation = escalation
        self._clock = clock

    async def submit(self, command: SubmitReceiptCommand):
        if command.telegram_user_id <= 0:
            raise ValueError("telegram user id must be positive")
        if not isinstance(command.input_type, ReceiptInputType):
            raise ValueError("unsupported receipt input type")

        transaction_reference = (
            command.transaction_reference.strip()
            if command.transaction_reference is not None
            else None
        )
        telegram_file_id = (
            command.telegram_file_id.strip()
            if command.telegram_file_id is not None
            else None
        )
        mime_type = command.mime_type.strip().lower() if command.mime_type is not None else None

        if command.input_type is ReceiptInputType.TEXT:
            if not transaction_reference or len(transaction_reference) > MAX_TRANSACTION_REFERENCE_LENGTH:
                raise ValueError("text receipt requires a valid transaction reference")
            if any(ord(char) < 32 or ord(char) == 127 for char in transaction_reference):
                raise ValueError("transaction reference contains control characters")
            if telegram_file_id is not None or mime_type is not None:
                raise ValueError("text receipt cannot contain image fields")
        else:
            if mime_type not in SUPPORTED_RECEIPT_MIME_TYPES:
                raise ValueError("unsupported receipt image type; JPEG, PNG, or WEBP is required")
            if not telegram_file_id:
                raise ValueError("receipt file id is required")
            if transaction_reference is not None:
                raise ValueError("image receipt cannot contain a transaction reference")

        idempotency_key = command.idempotency_key.strip()
        if not idempotency_key:
            raise ValueError("idempotency key is required")

        submitted_at = self._clock.now()
        if submitted_at.tzinfo is None:
            raise RuntimeError("receipt clock must return a timezone-aware datetime")

        reservation = await self._attempts.reserve_next_attempt(
            order_id=command.order_id,
            telegram_user_id=command.telegram_user_id,
            idempotency_key=idempotency_key,
            submitted_at=submitted_at,
            input_type=command.input_type,
            transaction_reference=transaction_reference,
            mime_type=mime_type,
            telegram_file_id=telegram_file_id,
        )
        attempt = reservation.attempt

        if reservation.replayed:
            return attempt

        try:
            if command.input_type is ReceiptInputType.IMAGE:
                await self._inspector.inspect(telegram_file_id, mime_type)  # type: ignore[arg-type]
            verification_status = await self._verifier.verify(attempt)
        except Exception as exc:
            reason = str(exc).strip() or "receipt processing failed"
            finalized = await self._finalize_failure(attempt, reason)
            if attempt.attempt_number == 3:
                await self._escalation.escalate(command.order_id, finalized.attempt_id, reason)
            raise

        if verification_status is ReceiptAttemptStatus.VERIFIED:
            return await self._attempts.finalize(
                attempt.attempt_id,
                ReceiptAttemptStatus.VERIFIED,
            )

        reason = "receipt could not be verified"
        finalized = await self._finalize_failure(attempt, reason)
        if attempt.attempt_number == 3:
            await self._escalation.escalate(command.order_id, finalized.attempt_id, reason)
        raise ValueError(reason)

    async def _finalize_failure(self, attempt: ReceiptAttempt, reason: str) -> ReceiptAttempt:
        status = (
            ReceiptAttemptStatus.ESCALATED
            if attempt.attempt_number == 3
            else ReceiptAttemptStatus.FAILED
        )
        return await self._attempts.finalize(attempt.attempt_id, status, reason)
