from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.application.receipt_ports import ReceiptAttemptRepository, ReceiptReservation
from app.application.submit_receipt import SubmitReceiptCommand, SubmitReceiptService
from app.domain.receipt_attempt import ReceiptAttempt, ReceiptAttemptStatus, ReceiptInputType


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
        input_type=ReceiptInputType.IMAGE,
        transaction_reference=None,
        failure_reason="failure" if status in (ReceiptAttemptStatus.FAILED, ReceiptAttemptStatus.ESCALATED) else None,
    )


def build_service(attempts, inspector, verifier, escalation, submitted_at):
    return SubmitReceiptService(
        attempts=attempts,
        inspector=inspector,
        verifier=verifier,
        escalation=escalation,
        clock=FixedClock(submitted_at),
    )


def command(order_id: UUID, **overrides):
    values = {
        "order_id": order_id,
        "telegram_user_id": 7001,
        "input_type": ReceiptInputType.IMAGE,
        "transaction_reference": None,
        "telegram_file_id": "telegram-file-1",
        "mime_type": "image/png",
        "idempotency_key": "telegram-update-123",
    }
    values.update(overrides)
    return SubmitReceiptCommand(**values)


@pytest.mark.asyncio
async def test_image_submission_inspects_image_and_verifies(order_id, submitted_at):
    attempts = AsyncMock(spec=ReceiptAttemptRepository)
    inspector = AsyncMock()
    verifier = AsyncMock()
    escalation = AsyncMock()
    attempt = build_attempt(order_id, submitted_at)
    attempts.reserve_next_attempt.return_value = ReceiptReservation(attempt=attempt, replayed=False)
    verifier.verify.return_value = ReceiptAttemptStatus.VERIFIED
    attempts.finalize.return_value = attempt

    await build_service(attempts, inspector, verifier, escalation, submitted_at).submit(
        command(order_id, telegram_file_id=" telegram-file-1 ", idempotency_key=" telegram-update-123 ")
    )

    attempts.reserve_next_attempt.assert_awaited_once_with(
        order_id=order_id,
        telegram_user_id=7001,
        idempotency_key="telegram-update-123",
        submitted_at=submitted_at,
        input_type=ReceiptInputType.IMAGE,
        transaction_reference=None,
        mime_type="image/png",
        telegram_file_id="telegram-file-1",
    )
    inspector.inspect.assert_awaited_once_with("telegram-file-1", "image/png")
    verifier.verify.assert_awaited_once_with(attempt)
    attempts.finalize.assert_awaited_once_with(attempt.attempt_id, ReceiptAttemptStatus.VERIFIED)


@pytest.mark.asyncio
async def test_text_submission_is_rejected_before_reservation(order_id, submitted_at):
    attempts = AsyncMock(spec=ReceiptAttemptRepository)
    service = build_service(attempts, AsyncMock(), AsyncMock(), AsyncMock(), submitted_at)

    with pytest.raises(ValueError, match="text receipt submission is not supported"):
        await service.submit(command(
            order_id,
            input_type=ReceiptInputType.TEXT,
            transaction_reference="SC-123456",
            telegram_file_id=None,
            mime_type=None,
        ))

    attempts.reserve_next_attempt.assert_not_awaited()


@pytest.mark.asyncio
async def test_image_submission_rejects_transaction_reference(order_id, submitted_at):
    attempts = AsyncMock(spec=ReceiptAttemptRepository)
    service = build_service(attempts, AsyncMock(), AsyncMock(), AsyncMock(), submitted_at)

    with pytest.raises(ValueError, match="image receipt cannot contain a transaction reference"):
        await service.submit(command(order_id, transaction_reference="SC-123456"))

    attempts.reserve_next_attempt.assert_not_awaited()


@pytest.mark.asyncio
async def test_replayed_receipt_does_not_reprocess(order_id, submitted_at):
    attempts = AsyncMock(spec=ReceiptAttemptRepository)
    inspector = AsyncMock()
    verifier = AsyncMock()
    escalation = AsyncMock()
    replayed = build_attempt(order_id, submitted_at, status=ReceiptAttemptStatus.VERIFIED)
    attempts.reserve_next_attempt.return_value = ReceiptReservation(attempt=replayed, replayed=True)

    result = await build_service(attempts, inspector, verifier, escalation, submitted_at).submit(command(order_id))

    assert result is replayed
    inspector.inspect.assert_not_awaited()
    verifier.verify.assert_not_awaited()
    attempts.finalize.assert_not_awaited()


@pytest.mark.asyncio
async def test_third_failure_escalates(order_id, submitted_at):
    attempts = AsyncMock(spec=ReceiptAttemptRepository)
    inspector = AsyncMock()
    verifier = AsyncMock()
    escalation = AsyncMock()
    attempt = build_attempt(order_id, submitted_at, attempt_number=3)
    finalized = build_attempt(order_id, submitted_at, attempt_number=3, status=ReceiptAttemptStatus.ESCALATED)
    attempts.reserve_next_attempt.return_value = ReceiptReservation(attempt=attempt, replayed=False)
    attempts.finalize.return_value = finalized
    inspector.inspect.side_effect = ValueError("invalid receipt image")

    with pytest.raises(ValueError, match="invalid receipt image"):
        await build_service(attempts, inspector, verifier, escalation, submitted_at).submit(command(order_id))

    attempts.finalize.assert_awaited_once_with(attempt.attempt_id, ReceiptAttemptStatus.ESCALATED, "invalid receipt image")
    escalation.escalate.assert_awaited_once_with(order_id, finalized.attempt_id, "invalid receipt image")


@pytest.mark.asyncio
async def test_missing_idempotency_key_is_rejected_before_reservation(order_id, submitted_at):
    attempts = AsyncMock(spec=ReceiptAttemptRepository)
    service = build_service(attempts, AsyncMock(), AsyncMock(), AsyncMock(), submitted_at)

    with pytest.raises(ValueError, match="idempotency key is required"):
        await service.submit(command(order_id, idempotency_key="   "))

    attempts.reserve_next_attempt.assert_not_awaited()
