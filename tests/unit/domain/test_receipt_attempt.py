from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.domain.receipt_attempt import ReceiptAttempt, ReceiptAttemptStatus, ReceiptInputType


def build(**overrides):
    values = {
        "attempt_id": uuid4(),
        "order_id": uuid4(),
        "attempt_number": 1,
        "mime_type": "image/png",
        "telegram_file_id": "file-1",
        "submitted_at": datetime(2026, 8, 29, tzinfo=timezone.utc),
        "status": ReceiptAttemptStatus.PROCESSING,
    }
    values.update(overrides)
    return ReceiptAttempt(**values)


def test_text_attempt_requires_reference_and_excludes_image_fields():
    attempt = build(
        input_type=ReceiptInputType.TEXT,
        transaction_reference="SC-123456",
        mime_type=None,
        telegram_file_id=None,
    )
    assert attempt.input_type is ReceiptInputType.TEXT
    assert attempt.transaction_reference == "SC-123456"


def test_text_attempt_rejects_image_fields():
    with pytest.raises(ValueError, match="text receipt cannot contain image fields"):
        build(input_type=ReceiptInputType.TEXT, transaction_reference="SC-123456")


def test_image_attempt_requires_supported_mime_and_file_id():
    with pytest.raises(ValueError, match="unsupported receipt MIME type"):
        build(mime_type="application/pdf")
    with pytest.raises(ValueError, match="image receipt requires a Telegram file id"):
        build(telegram_file_id=None)


def test_image_attempt_rejects_transaction_reference():
    with pytest.raises(ValueError, match="image receipt cannot contain a transaction reference"):
        build(transaction_reference="SC-123456")


def test_transaction_reference_rejects_control_characters():
    with pytest.raises(ValueError, match="control characters"):
        build(input_type=ReceiptInputType.TEXT, transaction_reference="SC-123\n456", mime_type=None, telegram_file_id=None)
