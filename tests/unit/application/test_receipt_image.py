from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from app.application.receipt_image import (
    MAX_RECEIPT_BYTES,
    MAX_RECEIPT_HEIGHT,
    MAX_RECEIPT_PIXELS,
    ReceiptImageInspectorImpl,
    ReceiptImageValidationError,
)


def _image_bytes(image_format: str, size: tuple[int, int] = (100, 100)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (255, 255, 255)).save(buffer, format=image_format)
    return buffer.getvalue()


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mime_type", "image_format"),
    [
        ("image/jpeg", "JPEG"),
        ("image/png", "PNG"),
        ("image/webp", "WEBP"),
    ],
)
async def test_supported_image_types_are_accepted(mime_type: str, image_format: str) -> None:
    inspector = ReceiptImageInspectorImpl()
    content = _image_bytes(image_format)
    result = await inspector.inspect_bytes(content, mime_type)
    assert result.mime_type == mime_type
    assert result.width == 100
    assert result.height == 100
    assert result.content == content


@pytest.mark.asyncio
async def test_declared_mime_must_match_actual_content() -> None:
    inspector = ReceiptImageInspectorImpl()
    content = _image_bytes("PNG")
    with pytest.raises(ReceiptImageValidationError, match="does not match"):
        await inspector.inspect_bytes(content, "image/jpeg")


@pytest.mark.asyncio
async def test_corrupt_image_is_rejected() -> None:
    inspector = ReceiptImageInspectorImpl()
    with pytest.raises(ReceiptImageValidationError, match="safely decoded|valid supported"):
        await inspector.inspect_bytes(b"not-an-image", "image/png")


@pytest.mark.asyncio
async def test_dimensions_are_bounded_before_decode() -> None:
    inspector = ReceiptImageInspectorImpl()
    too_wide = (MAX_RECEIPT_HEIGHT + 1, 1)
    content = _image_bytes("PNG", too_wide)
    with pytest.raises(ReceiptImageValidationError, match="dimensions exceed"):
        await inspector.inspect_bytes(content, "image/png")


@pytest.mark.asyncio
async def test_pixel_budget_is_enforced() -> None:
    inspector = ReceiptImageInspectorImpl()
    width = MAX_RECEIPT_PIXELS // 2 + 1
    content = _image_bytes("PNG", (width, 2))
    with pytest.raises(ReceiptImageValidationError, match="too many pixels"):
        await inspector.inspect_bytes(content, "image/png")
