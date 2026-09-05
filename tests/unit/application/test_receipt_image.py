import pytest

from app.application.receipt_image import (
    MAX_RECEIPT_BYTES,
    ReceiptImageInspectorImpl,
    ReceiptImageValidationError,
)


@pytest.mark.asyncio
async def test_empty_content_is_rejected() -> None:
    inspector = ReceiptImageInspectorImpl()
    with pytest.raises(ReceiptImageValidationError, match="empty"):
        await inspector.inspect_bytes(b"", "image/png")


@pytest.mark.asyncio
async def test_unsupported_mime_is_rejected() -> None:
    inspector = ReceiptImageInspectorImpl()
    with pytest.raises(ReceiptImageValidationError, match="unsupported"):
        await inspector.inspect_bytes(b"data", "application/pdf")


@pytest.mark.asyncio
async def test_oversized_content_is_rejected_before_decode() -> None:
    inspector = ReceiptImageInspectorImpl()
    with pytest.raises(ReceiptImageValidationError, match="5 MB"):
        await inspector.inspect_bytes(b"x" * (MAX_RECEIPT_BYTES + 1), "image/png")
