from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.receipt_ports import ReceiptAttemptRepository, ReceiptReservation
from app.application.submit_customer_receipt import SubmitCustomerReceiptCommand, SubmitCustomerReceiptService
from app.domain.receipt_attempt import ReceiptAttempt, ReceiptAttemptStatus, ReceiptInputType


def build_attempt(order_id, status=ReceiptAttemptStatus.PROCESSING):
    return ReceiptAttempt(
        attempt_id=uuid4(),
        order_id=order_id,
        attempt_number=1,
        mime_type="image/png",
        telegram_file_id="file-1",
        submitted_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        status=status,
    )


@pytest.mark.asyncio
async def test_customer_receipt_is_validated_then_submitted_for_manual_review():
    order_id = uuid4()
    attempts = AsyncMock(spec=ReceiptAttemptRepository)
    inspector = AsyncMock()
    clock = AsyncMock()
    submitted_at = datetime(2026, 9, 18, tzinfo=timezone.utc)
    clock.now = lambda: submitted_at
    processing = build_attempt(order_id)
    submitted = build_attempt(order_id, ReceiptAttemptStatus.SUBMITTED)
    attempts.reserve_next_attempt.return_value = ReceiptReservation(processing, replayed=False)
    attempts.finalize.return_value = submitted
    inspector.inspect_bytes.return_value = type(
        "Inspected",
        (),
        {"mime_type": "image/png"},
    )()

    result = await SubmitCustomerReceiptService(attempts, inspector, clock).submit(
        SubmitCustomerReceiptCommand(
            order_id=order_id,
            telegram_user_id=7001,
            telegram_file_id=" file-1 ",
            declared_mime_type="image/png",
            idempotency_key=" receipt-1 ",
        ),
        b"valid-image-bytes",
    )

    assert result.status is ReceiptAttemptStatus.SUBMITTED
    inspector.inspect_bytes.assert_awaited_once_with(b"valid-image-bytes", "image/png")
    attempts.reserve_next_attempt.assert_awaited_once()
    attempts.finalize.assert_awaited_once_with(processing.attempt_id, ReceiptAttemptStatus.SUBMITTED)


@pytest.mark.asyncio
async def test_invalid_image_never_reserves_receipt():
    attempts = AsyncMock(spec=ReceiptAttemptRepository)
    inspector = AsyncMock()
    clock = AsyncMock()
    clock.now = lambda: datetime(2026, 9, 18, tzinfo=timezone.utc)
    inspector.inspect_bytes.side_effect = ValueError("invalid image")

    with pytest.raises(ValueError, match="invalid image"):
        await SubmitCustomerReceiptService(attempts, inspector, clock).submit(
            SubmitCustomerReceiptCommand(
                order_id=uuid4(),
                telegram_user_id=7001,
                telegram_file_id="file-1",
                declared_mime_type="image/png",
                idempotency_key="receipt-2",
            ),
            b"bad",
        )

    attempts.reserve_next_attempt.assert_not_awaited()


@pytest.mark.asyncio
async def test_replay_does_not_finalize_again():
    order_id = uuid4()
    attempts = AsyncMock(spec=ReceiptAttemptRepository)
    inspector = AsyncMock()
    clock = AsyncMock()
    clock.now = lambda: datetime(2026, 9, 18, tzinfo=timezone.utc)
    submitted = build_attempt(order_id, ReceiptAttemptStatus.SUBMITTED)
    attempts.reserve_next_attempt.return_value = ReceiptReservation(submitted, replayed=True)

    result = await SubmitCustomerReceiptService(attempts, inspector, clock).submit(
        SubmitCustomerReceiptCommand(
            order_id=order_id,
            telegram_user_id=7001,
            telegram_file_id="file-1",
            declared_mime_type="image/png",
            idempotency_key="receipt-replay",
        ),
        b"valid",
    )

    assert result is submitted
    attempts.finalize.assert_not_awaited()


@pytest.mark.asyncio
async def test_text_transaction_reference_is_submitted_for_manual_review():
    order_id = uuid4()
    attempts = AsyncMock(spec=ReceiptAttemptRepository)
    inspector = AsyncMock()
    clock = AsyncMock()
    clock.now = lambda: datetime(2026, 9, 25, tzinfo=timezone.utc)
    processing = ReceiptAttempt(
        attempt_id=uuid4(),
        order_id=order_id,
        attempt_number=1,
        mime_type=None,
        telegram_file_id=None,
        submitted_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
        status=ReceiptAttemptStatus.PROCESSING,
        input_type=ReceiptInputType.TEXT,
        transaction_reference="SC-12345",
    )
    submitted = ReceiptAttempt(
        attempt_id=processing.attempt_id,
        order_id=order_id,
        attempt_number=1,
        mime_type=None,
        telegram_file_id=None,
        submitted_at=processing.submitted_at,
        status=ReceiptAttemptStatus.SUBMITTED,
        input_type=ReceiptInputType.TEXT,
        transaction_reference="SC-12345",
    )
    attempts.reserve_next_attempt.return_value = ReceiptReservation(processing, replayed=False)
    attempts.finalize.return_value = submitted

    result = await SubmitCustomerReceiptService(attempts, inspector, clock).submit(
        SubmitCustomerReceiptCommand(
            order_id=order_id,
            telegram_user_id=7001,
            idempotency_key="receipt-text-1",
            input_type=ReceiptInputType.TEXT,
            transaction_reference=" SC-12345 ",
        )
    )

    assert result.status is ReceiptAttemptStatus.SUBMITTED
    inspector.inspect_bytes.assert_not_awaited()
    attempts.reserve_next_attempt.assert_awaited_once_with(
        order_id, 7001, "receipt-text-1", clock.now(), ReceiptInputType.TEXT, "SC-12345", None, None
    )
    attempts.finalize.assert_awaited_once_with(processing.attempt_id, ReceiptAttemptStatus.SUBMITTED)
