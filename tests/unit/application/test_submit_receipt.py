from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.application.receipt_ports import ReceiptAttemptRepository, ReceiptReservation
from app.application.submit_receipt import SubmitReceiptCommand, SubmitReceiptService
from app.domain.receipt_attempt import ReceiptAttempt, ReceiptAttemptStatus


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def now(self) -> datetime:
        return self._value


@pytest.fixture
def order_id() -> UUID:
    return uuid4()


@pytest.fixture
def submitted_at() -> datetime:
    return datetime(2026, 8, 29, 18, 30, tzinfo=timezone.utc)


def build_attempt(
    order_id: UUID,
    submitted_at: datetime,
    *,
    attempt_number: int = 1,
    status: ReceiptAttemptStatus = ReceiptAttemptStatus.PROCESSING,
) -> ReceiptAttempt:
    return ReceiptAttempt(
        attempt_id=uuid4(),
        order_id=order_id,
        attempt_number=attempt_number,
        mime_type="image/png",
        telegram_file_id="telegram-file-1",
        submitted_at=submitted_at,
        status=status,
    )


@pytest.mark.asyncio
async def test_submit_receipt_passes_idempotency_key_to_reservation(
    order_id: UUID,
    submitted_at: datetime,
) -> None:
    attempts = AsyncMock(spec=ReceiptAttemptRepository)
    inspector = AsyncMock()
    verifier = AsyncMock()
    escalation = AsyncMock()
    attempt = build_attempt(order_id, submitted_at)
    attempts.reserve_next_attempt.return_value = ReceiptReservation(attempt=attempt, replayed=False)
    verifier.verify.return_value = ReceiptAttemptStatus.VERIFIED
    attempts.finalize.return_value = attempt

    service = SubmitReceiptService(
        attempts=attempts,
        inspector=inspector,
        verifier=verifier,
        escalation=escalation,
        clock=FixedClock(submitted_at),
    )

    await service.submit(
        SubmitReceiptCommand(
            order_id=order_id,
            telegram_file_id=" telegram-file-1 ",
            mime_type="image/png",
            idempotency_key=" telegram-update-123 ",
        )
    )

    attempts.reserve_next_attempt.assert_awaited_once_with(
        order_id=order_id,
        idempotency_key="telegram-update-123",
        submitted_at=submitted_at,
        mime_type="image/png",
        telegram_file_id="telegram-file-1",
    )
    inspector.inspect.assert_awaited_once_with("telegram-file-1", "image/png")
    verifier.verify.assert_awaited_once_with(attempt)


@pytest.mark.asyncio
async def test_replayed_receipt_does_not_reprocess_or_finalize(
    order_id: UUID,
    submitted_at: datetime,
) -> None:
    attempts = AsyncMock(spec=ReceiptAttemptRepository)
    inspector = AsyncMock()
    verifier = AsyncMock()
    escalation = AsyncMock()
    replayed_attempt = build_attempt(
        order_id,
        submitted_at,
        status=ReceiptAttemptStatus.VERIFIED,
    )
    attempts.reserve_next_attempt.return_value = ReceiptReservation(
        attempt=replayed_attempt,
        replayed=True,
    )

    service = SubmitReceiptService(
        attempts=attempts,
        inspector=inspector,
        verifier=verifier,
        escalation=escalation,
        clock=FixedClock(submitted_at),
    )

    result = await service.submit(
        SubmitReceiptCommand(
            order_id=order_id,
            telegram_file_id="telegram-file-1",
            mime_type="image/png",
            idempotency_key="telegram-update-123",
        )
    )

    assert result is replayed_attempt
    inspector.inspect.assert_not_awaited()
    verifier.verify.assert_not_awaited()
    attempts.finalize.assert_not_awaited()
    escalation.escalate.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_idempotency_key_is_rejected_before_reservation(
    order_id: UUID,
    submitted_at: datetime,
) -> None:
    attempts = AsyncMock(spec=ReceiptAttemptRepository)
    inspector = AsyncMock()
    verifier = AsyncMock()
    escalation = AsyncMock()

    service = SubmitReceiptService(
        attempts=attempts,
        inspector=inspector,
        verifier=verifier,
        escalation=escalation,
        clock=FixedClock(submitted_at),
    )

    with pytest.raises(ValueError, match="idempotency key is required"):
        await service.submit(
            SubmitReceiptCommand(
                order_id=order_id,
                telegram_file_id="telegram-file-1",
                mime_type="image/png",
                idempotency_key="   ",
            )
        )

    attempts.reserve_next_attempt.assert_not_awaited()
