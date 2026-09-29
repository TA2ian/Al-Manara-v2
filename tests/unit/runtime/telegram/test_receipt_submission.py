from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.submit_receipt import SubmitReceiptCommand
from app.domain.receipt_attempt import ReceiptInputType
from app.runtime.telegram.receipt_submission import TelegramReceiptHandler, TelegramReceiptInput


@pytest.mark.asyncio
async def test_text_receipt_is_rejected_before_submission():
    submission = AsyncMock()
    handler = TelegramReceiptHandler(submission=submission)

    response = await handler.submit(
        TelegramReceiptInput(
            user_id=7001,
            order_id=uuid4(),
            input_type=ReceiptInputType.TEXT,
            transaction_reference="  SC-123456  ",
            idempotency_key="update-1",
        )
    )

    assert response.ok is False
    assert submission.submit.await_count == 0


@pytest.mark.asyncio
async def test_image_receipt_is_forwarded_as_image_data():
    submission = AsyncMock()
    handler = TelegramReceiptHandler(submission=submission)

    response = await handler.submit(
        TelegramReceiptInput(
            user_id=7001,
            order_id=uuid4(),
            input_type=ReceiptInputType.IMAGE,
            telegram_file_id="file-1",
            mime_type="IMAGE/PNG",
            idempotency_key="update-2",
        )
    )

    assert response.ok is True
    command = submission.submit.await_args.args[0]
    assert isinstance(command, SubmitReceiptCommand)
    assert command.input_type is ReceiptInputType.IMAGE
    assert command.transaction_reference is None
    assert command.telegram_file_id == "file-1"
    assert command.mime_type == "image/png"


@pytest.mark.asyncio
async def test_text_receipt_rejects_image_fields():
    submission = AsyncMock()
    handler = TelegramReceiptHandler(submission=submission)

    response = await handler.submit(
        TelegramReceiptInput(
            user_id=7001,
            order_id=uuid4(),
            input_type=ReceiptInputType.TEXT,
            transaction_reference="SC-123456",
            telegram_file_id="file-1",
            idempotency_key="update-3",
        )
    )

    assert response.ok is False
    submission.submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_image_receipt_rejects_transaction_reference():
    submission = AsyncMock()
    handler = TelegramReceiptHandler(submission=submission)

    response = await handler.submit(
        TelegramReceiptInput(
            user_id=7001,
            order_id=uuid4(),
            input_type=ReceiptInputType.IMAGE,
            transaction_reference="SC-123456",
            telegram_file_id="file-1",
            mime_type="image/png",
            idempotency_key="update-4",
        )
    )

    assert response.ok is False
    submission.submit.assert_not_awaited()
