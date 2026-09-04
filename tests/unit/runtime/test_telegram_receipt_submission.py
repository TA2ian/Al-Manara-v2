from uuid import UUID

import pytest

from app.runtime.telegram.receipt_submission import (
    ReceiptMessages,
    TelegramReceiptHandler,
    TelegramReceiptInput,
)


ORDER_ID = UUID("11111111-1111-1111-1111-111111111111")


class Submission:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    async def submit(self, command):
        self.calls.append(command)
        if self.error:
            raise self.error
        return object()


def data(**overrides):
    values = {
        "user_id": 7,
        "order_id": ORDER_ID,
        "telegram_file_id": "telegram-file",
        "mime_type": "image/jpeg",
        "idempotency_key": "receipt-1",
    }
    values.update(overrides)
    return TelegramReceiptInput(**values)


@pytest.mark.asyncio
async def test_submit_accepts_valid_receipt():
    service = Submission()
    response = await TelegramReceiptHandler(service).submit(data())
    assert response.ok is True
    assert response.text == ReceiptMessages.ACCEPTED
    assert service.calls[0].order_id == ORDER_ID


@pytest.mark.asyncio
async def test_submit_rejects_invalid_input_before_service_call():
    service = Submission()
    response = await TelegramReceiptHandler(service).submit(data(user_id=0))
    assert response.ok is False
    assert response.text == ReceiptMessages.INVALID
    assert service.calls == []


@pytest.mark.asyncio
async def test_submit_maps_validation_failure_to_safe_message():
    service = Submission(ValueError("internal validation detail"))
    response = await TelegramReceiptHandler(service).submit(data())
    assert response.ok is False
    assert response.text == ReceiptMessages.FAILED
    assert "internal validation detail" not in response.text


@pytest.mark.asyncio
async def test_submit_hides_unexpected_errors():
    service = Submission(RuntimeError("database failure"))
    response = await TelegramReceiptHandler(service).submit(data())
    assert response.ok is False
    assert response.text == ReceiptMessages.ERROR
    assert "database failure" not in response.text
